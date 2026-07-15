#!/usr/bin/env python3
"""Rebuild the recovered HOMR route from public upstream source and assets."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    compare_records,
    extract_snapshot,
    load_records,
    run_logged,
    sha256_file,
)

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
OUTPUT_REL = Path("logs/issue245_fresh_upstream_homr_probe")
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
PDFSCORE_SOURCE_REF = "bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7"
HOMR_SOURCE_COMMIT = "864e2882f7a41afcf8f16654728a473ae56826d6"
HOMR_REPOSITORY = "https://github.com/liebharc/homr.git"
IMAGE_TAG = f"pdfscorebar-issue245-fresh-upstream-homr:{HOMR_SOURCE_COMMIT[:12]}"


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
    parser.add_argument("--keep-image", action="store_true")
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
    output_root = main_repo / OUTPUT_REL
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; rerun with --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    canonical = main_repo / CANONICAL_REL
    historical_detection = main_repo / HISTORICAL_DETECTION_REL
    if not canonical.is_file():
        raise FileNotFoundError(canonical)
    actual_input_hash = sha256_file(canonical)
    if actual_input_hash != CANONICAL_SHA256:
        raise RuntimeError(
            "Canonical image hash mismatch: "
            f"expected={CANONICAL_SHA256} actual={actual_input_hash}"
        )
    if not historical_detection.is_file():
        raise FileNotFoundError(historical_detection)

    report_path = output_root / "fresh_upstream_homr_probe_report.json"
    report: dict[str, Any] = {
        "schema_version": "issue245.fresh_upstream_homr_probe.v1",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "isolation": {
            "pdfscore_source_ref": PDFSCORE_SOURCE_REF,
            "homr_repository": HOMR_REPOSITORY,
            "homr_source_commit": HOMR_SOURCE_COMMIT,
            "model_source": "public HOMR onnx_checkpoints release assets",
            "numpy": "2.2.6",
            "opencv_python_headless": "4.12.0.88",
            "onnxruntime_gpu": "1.22.0",
            "base_image": args.base_image,
            "image_tag": IMAGE_TAG,
            "variable": "fresh public upstream source and release assets",
        },
        "input": {"path": str(canonical), "sha256": actual_input_hash},
        "historical_detection": str(historical_detection),
    }
    write_report(report_path, report)

    try:
        if args.rebuild or not image_exists(worktree):
            build_command = [
                "docker",
                "build",
                "--file",
                str(worktree / "tools/issue245/Dockerfile.fresh_upstream_homr_probe"),
                "--build-arg",
                f"BASE_IMAGE={args.base_image}",
                "--build-arg",
                f"HOMR_REPOSITORY={HOMR_REPOSITORY}",
                "--build-arg",
                f"HOMR_COMMIT={HOMR_SOURCE_COMMIT}",
                "--tag",
                IMAGE_TAG,
            ]
            if args.rebuild:
                build_command.append("--no-cache")
            build_command.append(str(worktree))
            run_logged(
                build_command,
                output_root / "docker_build.log",
                cwd=worktree,
            )
        else:
            (output_root / "docker_build.log").write_text(
                f"Reused existing image {IMAGE_TAG}\n", encoding="utf-8"
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

        provenance_container = Path("/workspace") / OUTPUT_REL / "provenance.json"
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
                "tools/issue245/collect_local_homr_probe_provenance.py",
                "--output",
                str(provenance_container),
                "--expected-commit",
                HOMR_SOURCE_COMMIT,
            ],
            output_root / "provenance.log",
            cwd=worktree,
        )

        run_id = "issue245_fresh_upstream_homr_864e288"
        evaluator_container = Path("/workspace") / OUTPUT_REL / "evaluator"
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
                f"/workspace/{CANONICAL_REL}",
                "--output-root",
                str(evaluator_container),
                "--force-run-id",
                run_id,
                "--enable-segnet-cache",
            ],
            output_root / "evaluator.log",
            cwd=worktree,
        )

        detection_path = (
            output_root
            / "evaluator"
            / run_id
            / "page_001"
            / "page_001_detections.json"
        )
        if not detection_path.is_file():
            raise FileNotFoundError(f"Detection was not created: {detection_path}")

        historical_records = load_records(historical_detection)
        candidate_records = load_records(detection_path)
        report["result"] = {
            "status": "completed",
            "detection_path": str(detection_path),
            "detection_sha256": sha256_file(detection_path),
            "provenance_path": str(output_root / "provenance.json"),
            "comparison_to_retained_historical": compare_records(
                historical_records, candidate_records
            ),
        }
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
    finally:
        if not args.keep_image:
            subprocess.run(
                ["docker", "image", "rm", IMAGE_TAG],
                cwd=worktree,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        write_report(report_path, report)

    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
