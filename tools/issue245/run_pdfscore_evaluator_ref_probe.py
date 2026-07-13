#!/usr/bin/env python3
"""Compare current and historical PDFScoreBar evaluator sources with one HOMR runtime."""

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

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_HISTORICAL_REF = "edf7bf610c3355c34e660192e81f35b03fe91714"
OUTPUT_REL = Path("logs/issue245_pdfscore_evaluator_ref_probe")
CANONICAL_REL = Path(
    "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
)
CANONICAL_SHA256 = (
    "48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6"
)
HISTORICAL_DETECTION_REL = Path(
    "logs/hybrid_pipeline_bench/"
    "eval2_Va_Prokofiev_Symphony1_page_001_20260131_103421/"
    "baseline/page_001/page_001/page_001_detections.json"
)
HOMR_COMMIT = "2c6c65b00c836feb167d08c2553acec36ef68401"
IMAGE_TAG = f"pdfscorebar-issue245-evaluator-ref:{HOMR_COMMIT[:12]}"
SOURCE_FILES = (
    "src/homr_eval_scripts/homr_evaluator.py",
    "src/common/preprocessing.py",
    "src/common/thin_barline_finder.py",
    "src/common/barline_evaluation.py",
)


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
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> dict[str, Any]:
    possible: list[tuple[float, float, int, int]] = []
    for left_index, left_record in enumerate(left):
        left_box = left_record["box"]
        left_x = (left_box[0] + left_box[2]) / 2.0
        for right_index, right_record in enumerate(right):
            right_box = right_record["box"]
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
        record for index, record in enumerate(left) if index not in matched_left
    ]
    right_only = [
        record for index, record in enumerate(right) if index not in matched_right
    ]
    return {
        "left": summarize(left),
        "right": summarize(right),
        "matched_count": len(matched_left),
        "left_only": summarize(left_only),
        "right_only": summarize(right_only),
        "semantic_equal": not left_only and not right_only,
        "left_only_examples": left_only[:20],
        "right_only_examples": right_only[:20],
    }


def git_output(worktree: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def extract_snapshot(worktree: Path, ref: str, destination: Path) -> dict[str, Any]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    archive = subprocess.Popen(
        ["git", "archive", "--format=tar", ref, "src"],
        cwd=worktree,
        stdout=subprocess.PIPE,
    )
    assert archive.stdout is not None
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(destination)],
        stdin=archive.stdout,
        check=False,
    )
    archive.stdout.close()
    archive_returncode = archive.wait()
    if archive_returncode != 0 or extract.returncode != 0:
        raise RuntimeError(
            "Failed to extract historical src snapshot: "
            f"git_archive={archive_returncode} tar={extract.returncode}"
        )

    resolved = git_output(worktree, "rev-parse", ref)
    metadata = git_output(worktree, "show", "-s", "--format=%H%n%cI%n%s", resolved)
    return {
        "requested_ref": ref,
        "resolved_ref": resolved,
        "commit_metadata": metadata.splitlines(),
        "snapshot_root": str(destination),
    }


def source_hashes(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in SOURCE_FILES:
        path = root / relative
        records.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    return records


def ensure_image(
    worktree: Path,
    output_root: Path,
    *,
    base_image: str,
    rebuild: bool,
) -> None:
    image_exists = (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE_TAG],
            cwd=worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if image_exists and not rebuild:
        (output_root / "docker_build.log").write_text(
            f"Reused existing image {IMAGE_TAG}\n", encoding="utf-8"
        )
        return

    run_logged(
        [
            "docker",
            "build",
            "--file",
            "tools/issue245/Dockerfile.homr_revision_probe",
            "--build-arg",
            f"BASE_IMAGE={base_image}",
            "--build-arg",
            f"HOMR_COMMIT={HOMR_COMMIT}",
            "--tag",
            IMAGE_TAG,
            ".",
        ],
        output_root / "docker_build.log",
        cwd=worktree,
    )


def run_variant(
    name: str,
    *,
    worktree: Path,
    main_repo: Path,
    output_root: Path,
    snapshot_root: Path | None,
    force: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    output_host = output_root / name
    if output_host.exists():
        if not force:
            raise FileExistsError(f"Output already exists: {output_host}")
        shutil.rmtree(output_host)
    output_host.mkdir(parents=True)

    run_id = f"issue245_{name}"
    output_container = Path("/workspace") / OUTPUT_REL / name / "evaluator"
    mounts = [
        "-v",
        f"{worktree}:/workspace",
        "-v",
        f"{main_repo / 'logs'}:/workspace/logs",
        "-v",
        f"{main_repo / 'data/evaluation2'}:/workspace/data/evaluation2:ro",
        "-w",
        "/workspace",
    ]
    if snapshot_root is None:
        pythonpath = "/workspace"
        source_root = worktree
    else:
        mounts.extend(["-v", f"{snapshot_root}:/historical:ro"])
        pythonpath = "/historical:/historical/src:/workspace"
        source_root = snapshot_root

    result: dict[str, Any] = {
        "name": name,
        "source_root": str(source_root),
        "source_hashes": source_hashes(source_root),
        "status": "started",
    }
    try:
        run_logged(
            [
                "docker",
                "run",
                "--rm",
                "--gpus",
                "all",
                *mounts,
                "-e",
                f"PYTHONPATH={pythonpath}",
                IMAGE_TAG,
                "/opt/venv_pipeline/bin/python",
                "tools/issue245/run_homr_evaluator_compat.py",
                "--images",
                f"/workspace/{CANONICAL_REL}",
                "--output-root",
                str(output_container),
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
            raise FileNotFoundError(f"Detection was not created: {detection_path}")
        records = load_records(detection_path)
        result.update(
            {
                "status": "completed",
                "detection_path": str(detection_path),
                "detection_sha256": sha256_file(detection_path),
                "summary": summarize(records),
            }
        )
        return result, records
    except Exception as error:
        result.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        return result, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--historical-ref", default=DEFAULT_HISTORICAL_REF)
    parser.add_argument(
        "--base-image",
        default=os.environ.get("ISSUE245_REVISION_BASE_IMAGE", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--keep-image", action="store_true")
    args = parser.parse_args()

    worktree = Path(git_output(Path.cwd(), "rev-parse", "--show-toplevel"))
    main_repo = args.main_repo_root.resolve()
    output_root = main_repo / OUTPUT_REL
    output_root.mkdir(parents=True, exist_ok=True)

    canonical = main_repo / CANONICAL_REL
    historical_detection = main_repo / HISTORICAL_DETECTION_REL
    if not canonical.is_file():
        raise FileNotFoundError(f"Canonical image not found: {canonical}")
    actual_hash = sha256_file(canonical)
    if actual_hash != CANONICAL_SHA256:
        raise RuntimeError(
            f"Canonical hash mismatch: expected={CANONICAL_SHA256} actual={actual_hash}"
        )
    if not historical_detection.is_file():
        raise FileNotFoundError(
            f"Historical comparison detection not found: {historical_detection}"
        )

    snapshot_root = output_root / "historical_source_snapshot"
    snapshot = extract_snapshot(worktree, args.historical_ref, snapshot_root)
    current_ref = git_output(worktree, "rev-parse", "HEAD")

    report: dict[str, Any] = {
        "schema_version": "issue245.pdfscore_evaluator_ref_probe.v1",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "isolation": {
            "homr_commit": HOMR_COMMIT,
            "onnxruntime_gpu": "1.22.0",
            "image_tag": IMAGE_TAG,
            "variable": "PDFScoreBar src tree only",
        },
        "input": {"path": str(canonical), "sha256": actual_hash},
        "historical_detection": str(historical_detection),
        "current_ref": current_ref,
        "historical_source": snapshot,
        "variants": [],
    }

    try:
        ensure_image(
            worktree,
            output_root,
            base_image=args.base_image,
            rebuild=args.rebuild,
        )
        historical_records = load_records(historical_detection)
        variant_records: dict[str, list[dict[str, Any]]] = {}

        for name, root in (
            ("current_source_control", None),
            ("historical_source_edf7bf6", snapshot_root),
        ):
            result, records = run_variant(
                name,
                worktree=worktree,
                main_repo=main_repo,
                output_root=output_root,
                snapshot_root=root,
                force=args.force,
            )
            if records is not None:
                result["comparison_to_retained_historical"] = compare_records(
                    historical_records, records
                )
                variant_records[name] = records
            report["variants"].append(result)
            (output_root / "pdfscore_evaluator_ref_probe_report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

        if len(variant_records) == 2:
            report["current_vs_historical_source"] = compare_records(
                variant_records["current_source_control"],
                variant_records["historical_source_edf7bf6"],
            )
        report["status"] = (
            "completed"
            if len(variant_records) == 2
            else "partial_failure"
        )
    finally:
        if not args.keep_image:
            subprocess.run(
                ["docker", "image", "rm", IMAGE_TAG],
                cwd=worktree,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    report_path = output_root / "pdfscore_evaluator_ref_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
