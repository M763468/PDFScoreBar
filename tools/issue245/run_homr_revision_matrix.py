#!/usr/bin/env python3
"""Build and compare pinned HOMR revisions on the canonical Issue #245 page."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("tools/issue245/homr_revision_candidates.json")
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
OUTPUT_REL = Path("logs/issue245_homr_revision_matrix")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_logged(command: list[str], log_path: Path, *, cwd: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+", " ".join(command), flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        returncode = process.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions = payload.get("predictions", []) if isinstance(payload, dict) else []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(predictions):
        if not isinstance(item, dict):
            continue
        value = item.get("orig_bbox") or item.get("pred_bbox")
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(part) for part in value)
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "index": index,
                "box": [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                "system_index": item.get("system_index"),
                "staff_index": item.get("staff_index"),
            }
        )
    return records


def vertical_overlap_ratio(left: list[float], right: list[float]) -> float:
    overlap = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    denominator = min(left[3] - left[1], right[3] - right[1])
    return overlap / denominator if denominator > 0 else 0.0


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(records),
        "thin_barline_tagged_count": sum(
            1 for record in records if record.get("system_index") == -2
        ),
    }


def compare_records(
    historical: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> dict[str, Any]:
    possible: list[tuple[float, float, int, int]] = []
    for left_index, left in enumerate(historical):
        left_box = left["box"]
        left_x = (left_box[0] + left_box[2]) / 2.0
        for right_index, right in enumerate(candidate):
            right_box = right["box"]
            right_x = (right_box[0] + right_box[2]) / 2.0
            x_distance = abs(left_x - right_x)
            overlap = vertical_overlap_ratio(left_box, right_box)
            if x_distance <= 12.0 and overlap >= 0.5:
                possible.append((x_distance, -overlap, left_index, right_index))

    matched_left: set[int] = set()
    matched_right: set[int] = set()
    for _, _, left_index, right_index in sorted(possible):
        if left_index in matched_left or right_index in matched_right:
            continue
        matched_left.add(left_index)
        matched_right.add(right_index)

    left_only = [
        record for index, record in enumerate(historical) if index not in matched_left
    ]
    right_only = [
        record for index, record in enumerate(candidate) if index not in matched_right
    ]
    return {
        "historical": summarize(historical),
        "candidate": summarize(candidate),
        "matched_count": len(matched_left),
        "historical_only": summarize(left_only),
        "candidate_only": summarize(right_only),
        "semantic_equal": not left_only and not right_only,
        "historical_only_examples": left_only[:20],
        "candidate_only_examples": right_only[:20],
    }


def resolve_candidates(
    manifest: dict[str, Any], requested: list[str], run_all: bool
) -> list[dict[str, Any]]:
    candidates = manifest["candidates"]
    by_name = {candidate["name"]: candidate for candidate in candidates}
    if requested:
        unknown = sorted(set(requested) - set(by_name))
        if unknown:
            raise ValueError(f"Unknown candidate names: {', '.join(unknown)}")
        return [by_name[name] for name in requested]
    if run_all:
        return candidates
    return [candidate for candidate in candidates if candidate.get("default_stage")]


def docker_mounts(worktree: Path, main_repo: Path) -> list[str]:
    return [
        "-v",
        f"{worktree}:/workspace",
        "-v",
        f"{main_repo / 'logs'}:/workspace/logs",
        "-v",
        f"{main_repo / 'data/evaluation2'}:/workspace/data/evaluation2:ro",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
    ]


def run_candidate(
    candidate: dict[str, Any],
    *,
    manifest: dict[str, Any],
    worktree: Path,
    main_repo: Path,
    base_image: str,
    force: bool,
    rebuild: bool,
    keep_image: bool,
    historical_records: list[dict[str, Any]],
) -> dict[str, Any]:
    name = candidate["name"]
    commit = candidate["homr_commit"]
    short_commit = commit[:12]
    image_tag = f"pdfscorebar-issue245-homr-{name}:{short_commit}"
    output_host = main_repo / OUTPUT_REL / name
    output_container = Path("/workspace") / OUTPUT_REL / name

    if output_host.exists():
        if not force:
            raise FileExistsError(
                f"Output already exists for {name}; rerun with --force: {output_host}"
            )
        shutil.rmtree(output_host)
    output_host.mkdir(parents=True)

    result: dict[str, Any] = {
        "candidate": candidate,
        "image_tag": image_tag,
        "status": "started",
    }
    try:
        image_exists = (
            subprocess.run(
                ["docker", "image", "inspect", image_tag],
                cwd=worktree,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if rebuild or not image_exists:
            run_logged(
                [
                    "docker",
                    "build",
                    "--file",
                    "tools/issue245/Dockerfile.homr_revision_probe",
                    "--build-arg",
                    f"BASE_IMAGE={base_image}",
                    "--build-arg",
                    f"HOMR_COMMIT={commit}",
                    "--tag",
                    image_tag,
                    ".",
                ],
                output_host / "docker_build.log",
                cwd=worktree,
            )
        else:
            (output_host / "docker_build.log").write_text(
                f"Reused existing image {image_tag}\n", encoding="utf-8"
            )

        mounts = docker_mounts(worktree, main_repo)
        provenance_rel = OUTPUT_REL / name / "provenance.json"
        run_logged(
            [
                "docker",
                "run",
                "--rm",
                "--gpus",
                "all",
                *mounts,
                image_tag,
                "/opt/venv_pipeline/bin/python",
                "tools/issue245/collect_homr_revision_provenance.py",
                "--output",
                str(Path("/workspace") / provenance_rel),
                "--candidate-name",
                name,
                "--expected-commit",
                commit,
            ],
            output_host / "provenance.log",
            cwd=worktree,
        )

        run_id = f"issue245_{name}"
        evaluator_root = output_container / "evaluator"
        run_logged(
            [
                "docker",
                "run",
                "--rm",
                "--gpus",
                "all",
                *mounts,
                image_tag,
                "/opt/venv_pipeline/bin/python",
                "tools/issue245/run_homr_evaluator_compat.py",
                "--images",
                "/workspace/"
                + manifest["artifact"]["canonical_image"],
                "--output-root",
                str(evaluator_root),
                "--force-run-id",
                run_id,
                "--enable-segnet-cache",
            ],
            output_host / "evaluator.log",
            cwd=worktree,
        )

        detection_path = (
            output_host
            / "evaluator"
            / run_id
            / "page_001"
            / "page_001_detections.json"
        )
        if not detection_path.is_file():
            raise FileNotFoundError(f"Candidate detection was not created: {detection_path}")

        candidate_records = load_records(detection_path)
        result.update(
            {
                "status": "compared",
                "detection_path": str(detection_path),
                "provenance_path": str(output_host / "provenance.json"),
                "comparison": compare_records(historical_records, candidate_records),
            }
        )
    except Exception as error:
        result.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    finally:
        if not keep_image:
            subprocess.run(
                ["docker", "image", "rm", image_tag],
                cwd=worktree,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument(
        "--base-image",
        default=os.environ.get("ISSUE245_REVISION_BASE_IMAGE", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--keep-images", action="store_true")
    args = parser.parse_args()

    worktree = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    manifest_path = (worktree / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = resolve_candidates(manifest, args.candidate, args.all)
    main_repo = args.main_repo_root.resolve()

    canonical = main_repo / manifest["artifact"]["canonical_image"]
    historical_detection = main_repo / manifest["artifact"]["historical_detection"]
    if not canonical.is_file():
        raise FileNotFoundError(f"Canonical image not found: {canonical}")
    actual_hash = sha256_file(canonical)
    expected_hash = manifest["artifact"]["canonical_sha256"]
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Canonical image hash mismatch: expected={expected_hash} actual={actual_hash}"
        )
    if not historical_detection.is_file():
        raise FileNotFoundError(
            f"Historical comparison artifact not found: {historical_detection}"
        )

    output_root = main_repo / OUTPUT_REL
    output_root.mkdir(parents=True, exist_ok=True)
    historical_records = load_records(historical_detection)
    report = {
        "schema_version": "issue245.homr_revision_matrix.v1",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "input": {
            "path": str(canonical),
            "sha256": actual_hash,
        },
        "historical": {
            "detection_path": str(historical_detection),
            "count": len(historical_records),
        },
        "runtime_isolation": manifest["runtime_isolation"],
        "results": [],
    }

    for candidate in candidates:
        print(f"\n=== Issue #245 HOMR candidate: {candidate['name']} ===", flush=True)
        result = run_candidate(
            candidate,
            manifest=manifest,
            worktree=worktree,
            main_repo=main_repo,
            base_image=args.base_image,
            force=args.force,
            rebuild=args.rebuild,
            keep_image=args.keep_images,
            historical_records=historical_records,
        )
        report["results"].append(result)
        (output_root / "homr_revision_matrix_report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

    compared = [result for result in report["results"] if result["status"] == "compared"]
    report["status"] = "completed" if len(compared) == len(candidates) else "partial_failure"
    report["ranking"] = sorted(
        (
            {
                "name": result["candidate"]["name"],
                "matched_count": result["comparison"]["matched_count"],
                "historical_only": result["comparison"]["historical_only"]["count"],
                "candidate_only": result["comparison"]["candidate_only"]["count"],
            }
            for result in compared
        ),
        key=lambda item: (
            -item["matched_count"],
            item["historical_only"] + item["candidate_only"],
        ),
    )
    report_path = output_root / "homr_revision_matrix_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport: {report_path}")
    for item in report["ranking"]:
        print(
            f"{item['name']}: matched={item['matched_count']} "
            f"historical_only={item['historical_only']} "
            f"candidate_only={item['candidate_only']}"
        )
    return 0 if compared else 1


if __name__ == "__main__":
    raise SystemExit(main())
