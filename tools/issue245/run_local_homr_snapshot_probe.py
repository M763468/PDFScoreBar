#!/usr/bin/env python3
"""Probe the recovered clean local HOMR source/model snapshot on page 001."""

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
DEFAULT_LOCAL_HOMR = DEFAULT_MAIN_REPO / "external/homr"
OUTPUT_REL = Path("logs/issue245_local_homr_snapshot_probe")
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
IMAGE_TAG = f"pdfscorebar-issue245-local-homr:{HOMR_SOURCE_COMMIT[:12]}"
MODEL_HASHES = {
    "homr/segmentation/segnet_155-1240eedca553155b3c75fc9c7f643465383430a0.onnx": (
        "e6a7c1e84f8d2f19f20a47e0889be2392cd487d27fa77984e4877b86534dee83"
    ),
    "homr/transformer/decoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx": (
        "381646983d14f17a11e4be671aaf6e4f81727b3a9edf0cf4890109a321ffce68"
    ),
    "homr/transformer/encoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx": (
        "22a443b2ea18da82128ae52e85436d6fb4728ab68aee24adb2ac9dfc2003a30c"
    ),
}
EXPECTED_CLEAN_SOURCE_HASHES = {
    "homr/autocrop.py": (
        "b75671236cee61c2560cf19493ef3756b04e54cfcb00c8227660e74bc72eb3cf"
    ),
    "homr/main.py": (
        "d934880735af1174645d53fb44a4371a6ee7ceace1c5abb6230b153b130c9800"
    ),
    "homr/segmentation/config.py": (
        "7509df2f5a4848ca10ef61cfdc8f4741c2aa46bfa27fc8395c42e69b83237594"
    ),
    "homr/segmentation/inference_segnet.py": (
        "d1f8e59826b8fbea0a9c47adc3bc99d9013223e41b98aaf9a7016625fa29b259"
    ),
}


def git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def archive_commit(repo: Path, commit: str, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    archive = subprocess.Popen(
        ["git", "-C", str(repo), "archive", "--format=tar", commit],
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
            "Failed to archive local HOMR commit: "
            f"git_archive={archive_returncode} tar={extract.returncode}"
        )


def prepare_build_context(local_homr: Path, destination: Path) -> dict[str, Any]:
    actual_commit = git_output(local_homr, "rev-parse", HOMR_SOURCE_COMMIT)
    if actual_commit != HOMR_SOURCE_COMMIT:
        raise RuntimeError(
            f"Local HOMR commit mismatch: expected={HOMR_SOURCE_COMMIT} "
            f"actual={actual_commit}"
        )
    archive_commit(local_homr, HOMR_SOURCE_COMMIT, destination)

    source_records: list[dict[str, Any]] = []
    for relative, expected_hash in EXPECTED_CLEAN_SOURCE_HASHES.items():
        path = destination / relative
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Clean source hash mismatch for {relative}: "
                f"expected={expected_hash} actual={actual_hash}"
            )
        source_records.append(
            {"path": relative, "sha256": actual_hash, "source": "git_archive"}
        )

    model_records: list[dict[str, Any]] = []
    for relative, expected_hash in MODEL_HASHES.items():
        source = local_homr / relative
        if not source.is_file():
            raise FileNotFoundError(f"Recovered HOMR model not found: {source}")
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Recovered model hash mismatch for {relative}: "
                f"expected={expected_hash} actual={actual_hash}"
            )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        model_records.append(
            {
                "path": relative,
                "sha256": actual_hash,
                "size_bytes": target.stat().st_size,
                "source": str(source),
            }
        )

    return {
        "source_commit": HOMR_SOURCE_COMMIT,
        "source_records": source_records,
        "model_records": model_records,
        "excluded_dirty_changes": [
            {
                "path": "homr/segmentation/inference_segnet.py",
                "reason": "2026-01-17 provider-debug logging only; no inference semantics",
            },
            {
                "path": "homr/autocrop.py",
                "reason": "working-tree mtime 2026-03-10, after the retained artifact",
            },
            {
                "path": "pyproject.toml",
                "reason": "working-tree mtime 2026-03-14, after the retained artifact",
            },
        ],
    }


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--local-homr-root", type=Path, default=DEFAULT_LOCAL_HOMR)
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
    local_homr = args.local_homr_root.expanduser().resolve()
    output_root = main_repo / OUTPUT_REL
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; rerun with --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    canonical = main_repo / CANONICAL_REL
    historical_detection = main_repo / HISTORICAL_DETECTION_REL
    if sha256_file(canonical) != CANONICAL_SHA256:
        raise RuntimeError(f"Canonical image hash mismatch: {canonical}")
    if not historical_detection.is_file():
        raise FileNotFoundError(historical_detection)

    report_path = output_root / "local_homr_snapshot_probe_report.json"
    report: dict[str, Any] = {
        "schema_version": "issue245.local_homr_snapshot_probe.v1",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "isolation": {
            "pdfscore_source_ref": PDFSCORE_SOURCE_REF,
            "homr_source_commit": HOMR_SOURCE_COMMIT,
            "onnxruntime_gpu": "1.22.0",
            "base_image": args.base_image,
            "image_tag": IMAGE_TAG,
            "variable": "recovered clean HOMR source and retained model files",
        },
        "input": {"path": str(canonical), "sha256": CANONICAL_SHA256},
        "historical_detection": str(historical_detection),
    }

    try:
        build_context = output_root / "build_context"
        report["snapshot"] = prepare_build_context(local_homr, build_context)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        if args.rebuild or not image_exists(worktree):
            run_logged(
                [
                    "docker",
                    "build",
                    "--file",
                    str(worktree / "tools/issue245/Dockerfile.local_homr_snapshot_probe"),
                    "--build-arg",
                    f"BASE_IMAGE={args.base_image}",
                    "--build-arg",
                    f"HOMR_SOURCE_COMMIT={HOMR_SOURCE_COMMIT}",
                    "--tag",
                    IMAGE_TAG,
                    str(build_context),
                ],
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

        run_id = "issue245_local_homr_864e288"
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
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
