#!/usr/bin/env python3
"""Run the verified fresh public-upstream HOMR image on representative pages."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.issue245.run_fresh_upstream_homr_probe import (
    HOMR_REPOSITORY,
    HOMR_SOURCE_COMMIT,
    IMAGE_TAG,
    PDFSCORE_SOURCE_REF,
)
from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    compare_records,
    extract_snapshot,
    load_records,
    run_logged,
    sha256_file,
)

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_MANIFEST = Path("tools/issue245/fresh_upstream_representative_pages.json")
OUTPUT_REL = Path("logs/issue245_fresh_upstream_representative_probe")


def normalize_artifact_key(value: str) -> str:
    """Normalize score/page names across underscore, hyphen, and repeated-separator variants."""
    return "".join(character.lower() for character in value if character.isalnum())


def image_artifact_key(image_rel: Path) -> str:
    return normalize_artifact_key(f"{image_rel.parent.name}_{image_rel.stem}")


def resolve_historical_detection(
    root: Path, image_rel: Path, historical_run_date: str
) -> tuple[Path, Path]:
    """Resolve one retained batch artifact by normalized image key and batch date."""
    benchmark_root = root / "logs/hybrid_pipeline_bench"
    target_key = image_artifact_key(image_rel)
    matching_runs: list[Path] = []
    for run_dir in sorted(benchmark_root.glob(f"*_{historical_run_date}_*")):
        if not run_dir.is_dir():
            continue
        if target_key in normalize_artifact_key(run_dir.name):
            matching_runs.append(run_dir)

    resolved: list[tuple[Path, Path]] = []
    for run_dir in matching_runs:
        baseline_root = run_dir / "baseline"
        detections = sorted(
            path
            for path in baseline_root.rglob("page_*_detections.json")
            if path.is_file()
        )
        for detection in detections:
            resolved.append((run_dir, detection))

    if len(resolved) != 1:
        details = ", ".join(
            f"{run_dir.name}:{detection.relative_to(run_dir)}"
            for run_dir, detection in resolved[:10]
        )
        raise RuntimeError(
            "Expected one retained historical detection for "
            f"image={image_rel} date={historical_run_date}, found {len(resolved)}: "
            f"{details}"
        )
    return resolved[0]


def find_single_detection(root: Path) -> Path:
    matches = sorted(root.rglob("page_*_detections.json"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one generated detection under {root}, found {len(matches)}: "
            + ", ".join(str(path) for path in matches[:10])
        )
    return matches[0]


def image_exists(worktree: Path) -> bool:
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE_TAG],
            cwd=worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    worktree = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    main_repo = args.main_repo_root.expanduser().resolve()
    manifest_path = (worktree / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    historical_run_date = str(manifest["historical_run_date"])

    output_root = main_repo / OUTPUT_REL
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; rerun with --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    report_path = output_root / "fresh_upstream_representative_probe_report.json"
    report: dict[str, Any] = {
        "schema_version": "issue245.fresh_upstream_representative_probe.v2",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "isolation": {
            "pdfscore_source_ref": PDFSCORE_SOURCE_REF,
            "homr_repository": HOMR_REPOSITORY,
            "homr_source_commit": HOMR_SOURCE_COMMIT,
            "image_tag": IMAGE_TAG,
            "model_source": "public HOMR onnx_checkpoints release assets",
            "dependency_contract": {
                "numpy": "2.2.6",
                "opencv_python_headless": "4.12.0.88",
                "onnxruntime_gpu": "1.22.0",
            },
        },
        "manifest": str(manifest_path),
        "historical_run_date": historical_run_date,
        "pages": [],
    }
    write_report(report_path, report)

    try:
        if not image_exists(worktree):
            raise RuntimeError(
                f"Verified fresh image is missing: {IMAGE_TAG}. "
                "Run run_fresh_upstream_homr_probe.sh with --keep-image first."
            )

        pdfscore_snapshot = output_root / "pdfscore_source_snapshot"
        report["pdfscore_source"] = extract_snapshot(
            worktree, PDFSCORE_SOURCE_REF, pdfscore_snapshot
        )
        write_report(report_path, report)

        mounts = [
            "-v",
            f"{worktree}:/workspace",
            "-v",
            f"{main_repo / 'logs'}:/workspace/logs",
            "-v",
            f"{main_repo / 'data/evaluation2'}:/workspace/data/evaluation2:ro",
            "-v",
            f"{pdfscore_snapshot}:/historical:ro",
            "-w",
            "/workspace",
            "-e",
            "PYTHONPATH=/opt/issue245_homr:/historical:/historical/src:/workspace",
        ]

        for item in manifest["pages"]:
            page_id = str(item["page_id"])
            image_rel = Path(item["image"])
            image_host = main_repo / image_rel
            if not image_host.is_file():
                raise FileNotFoundError(f"Representative input is missing: {image_host}")
            historical_run, historical = resolve_historical_detection(
                main_repo, image_rel, historical_run_date
            )

            page_root = output_root / "pages" / page_id
            evaluator_host = page_root / "evaluator"
            evaluator_container = (
                Path("/workspace") / OUTPUT_REL / "pages" / page_id / "evaluator"
            )
            run_id = f"issue245_fresh_upstream_representative_{page_id}"
            run_logged(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--gpus",
                    "all",
                    *mounts,
                    IMAGE_TAG,
                    "/opt/venv_pipeline/bin/python",
                    "tools/issue245/run_homr_evaluator_compat.py",
                    "--images",
                    f"/workspace/{image_rel}",
                    "--output-root",
                    str(evaluator_container),
                    "--force-run-id",
                    run_id,
                    "--enable-segnet-cache",
                ],
                page_root / "evaluator.log",
                cwd=worktree,
            )

            candidate = find_single_detection(evaluator_host)
            historical_records = load_records(historical)
            candidate_records = load_records(candidate)
            comparison = compare_records(historical_records, candidate_records)
            report["pages"].append(
                {
                    "page_id": page_id,
                    "reasons": item.get("reasons", []),
                    "input": {
                        "path": str(image_host),
                        "sha256": sha256_file(image_host),
                        "artifact_key": image_artifact_key(image_rel),
                    },
                    "historical_run": str(historical_run),
                    "historical_detection": str(historical),
                    "candidate_detection": str(candidate),
                    "candidate_detection_sha256": sha256_file(candidate),
                    "comparison": comparison,
                }
            )
            write_report(report_path, report)

        report["all_semantic_equal"] = all(
            page["comparison"]["semantic_equal"] for page in report["pages"]
        )
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
    finally:
        write_report(report_path, report)

    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
