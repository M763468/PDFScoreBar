#!/usr/bin/env python3
"""Regenerate and compare the canonical 68 baseline HOMR pages."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue245.run_fresh_upstream_homr_probe import (
    HOMR_REPOSITORY,
    HOMR_SOURCE_COMMIT,
    IMAGE_TAG,
    PDFSCORE_SOURCE_REF,
)
from tools.issue245.run_fresh_upstream_representative_probe import (
    find_single_detection,
    image_artifact_key,
    image_exists,
    resolve_historical_detection,
)
from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    compare_records,
    extract_snapshot,
    load_records,
    run_logged,
    sha256_file,
)

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
IMAGE_ROOT_REL = Path("data/evaluation2/images")
OUTPUT_REL = Path("logs/issue245_fresh_upstream_full68_probe")
EXPECTED_PAGE_COUNT = 68
DEFAULT_HISTORICAL_RUN_DATE = "20260131"
CANONICAL_PAGE_SET_SOURCE = "tools/issue120/eval_full68_from_intermediates.py:SCORES"


def discover_canonical_images(image_root: Path) -> list[Path]:
    """Resolve the established Issue #120 page set, excluding covers and blanks."""
    images: list[Path] = []
    missing: list[Path] = []
    for score, pages in SCORES.items():
        for page in pages:
            path = image_root / score / f"{page}.png"
            if path.is_file():
                images.append(path)
            else:
                missing.append(path)
    if missing:
        raise RuntimeError(
            "Canonical Issue #120 image set is incomplete: "
            + ", ".join(str(path) for path in missing)
        )
    return images


def build_inventory(
    main_repo: Path,
    images: list[Path],
    historical_run_date: str,
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen_keys: dict[str, Path] = {}
    for ordinal, image_host in enumerate(images, start=1):
        image_rel = image_host.relative_to(main_repo)
        artifact_key = image_artifact_key(image_rel)
        previous = seen_keys.get(artifact_key)
        if previous is not None:
            raise RuntimeError(
                "Duplicate normalized artifact key: "
                f"key={artifact_key} first={previous} second={image_rel}"
            )
        seen_keys[artifact_key] = image_rel
        historical_run, historical_detection = resolve_historical_detection(
            main_repo,
            image_rel,
            historical_run_date,
        )
        inventory.append(
            {
                "ordinal": ordinal,
                "artifact_key": artifact_key,
                "image_rel": str(image_rel),
                "image_path": str(image_host),
                "image_sha256": sha256_file(image_host),
                "historical_run": str(historical_run),
                "historical_detection": str(historical_detection),
            }
        )
    return inventory


def aggregate_results(pages: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [page for page in pages if page.get("status") == "completed"]
    failed = [page for page in pages if page.get("status") == "failed"]
    differing = [
        page
        for page in completed
        if not page.get("comparison", {}).get("semantic_equal", False)
    ]
    return {
        "pages_completed": len(completed),
        "pages_failed": len(failed),
        "pages_semantic_equal": len(completed) - len(differing),
        "pages_different": len(differing),
        "historical_count": sum(
            page["comparison"]["left"]["count"] for page in completed
        ),
        "candidate_count": sum(
            page["comparison"]["right"]["count"] for page in completed
        ),
        "matched_count": sum(
            page["comparison"]["matched_count"] for page in completed
        ),
        "historical_only_count": sum(
            page["comparison"]["left_only"]["count"] for page in completed
        ),
        "candidate_only_count": sum(
            page["comparison"]["right_only"]["count"] for page in completed
        ),
        "historical_thin_barline_tagged_count": sum(
            page["comparison"]["left"]["thin_barline_tagged_count"]
            for page in completed
        ),
        "candidate_thin_barline_tagged_count": sum(
            page["comparison"]["right"]["thin_barline_tagged_count"]
            for page in completed
        ),
        "failed_artifact_keys": [page["artifact_key"] for page in failed],
        "differing_artifact_keys": [page["artifact_key"] for page in differing],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def load_existing_pages(report_path: Path) -> dict[str, dict[str, Any]]:
    if not report_path.is_file():
        return {}
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        str(page["artifact_key"]): page
        for page in payload.get("pages", [])
        if isinstance(page, dict) and page.get("artifact_key")
    }


def build_report(
    *,
    inventory: list[dict[str, Any]],
    historical_run_date: str,
    expected_pages: int,
    preflight_only: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "issue245.fresh_upstream_full68_probe.v2",
        "status": "preflight_completed" if preflight_only else "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "canonical_page_set_source": CANONICAL_PAGE_SET_SOURCE,
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
        "historical_run_date": historical_run_date,
        "expected_pages": expected_pages,
        "discovered_pages": len(inventory),
        "preflight": {
            "all_images_exist": True,
            "all_image_keys_unique": True,
            "all_historical_detections_resolved": True,
            "inventory": inventory,
        },
        "pages": [],
    }


def run_page(
    *,
    item: dict[str, Any],
    worktree: Path,
    output_root: Path,
    mounts: list[str],
    existing: dict[str, Any] | None,
    resume: bool,
) -> dict[str, Any]:
    artifact_key = str(item["artifact_key"])
    ordinal = int(item["ordinal"])
    page_key = f"{ordinal:03d}_{artifact_key}"
    page_root = output_root / "pages" / page_key
    evaluator_host = page_root / "evaluator"
    historical_detection = Path(str(item["historical_detection"]))
    result: dict[str, Any] = {**item, "page_key": page_key, "status": "running"}

    candidate: Path | None = None
    if resume and existing and existing.get("status") == "completed":
        existing_path = Path(str(existing.get("candidate_detection", "")))
        if existing_path.is_file():
            candidate = existing_path
            result["inference_reused"] = True

    if candidate is None:
        if evaluator_host.exists():
            shutil.rmtree(evaluator_host)
        image_rel = Path(str(item["image_rel"]))
        evaluator_container = (
            Path("/workspace") / OUTPUT_REL / "pages" / page_key / "evaluator"
        )
        run_id = f"issue245_fresh_upstream_full68_{ordinal:03d}"
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
        result["inference_reused"] = False

    comparison = compare_records(
        load_records(historical_detection),
        load_records(candidate),
    )
    result.update(
        {
            "status": "completed",
            "candidate_detection": str(candidate),
            "candidate_detection_sha256": sha256_file(candidate),
            "comparison": comparison,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument(
        "--historical-run-date",
        default=DEFAULT_HISTORICAL_RUN_DATE,
    )
    parser.add_argument("--expected-pages", type=int, default=EXPECTED_PAGE_COUNT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    if args.force and args.resume:
        raise ValueError("--force and --resume are mutually exclusive")

    worktree = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    main_repo = args.main_repo_root.expanduser().resolve()
    image_root = main_repo / IMAGE_ROOT_REL
    if not image_root.is_dir():
        raise FileNotFoundError(f"Canonical image root is missing: {image_root}")

    output_root = main_repo / OUTPUT_REL
    report_path = output_root / "fresh_upstream_full68_probe_report.json"
    existing_pages: dict[str, dict[str, Any]] = {}
    if output_root.exists():
        if args.force:
            shutil.rmtree(output_root)
        elif args.resume:
            existing_pages = load_existing_pages(report_path)
        else:
            raise FileExistsError(
                f"Output exists; rerun with --force or --resume: {output_root}"
            )
    output_root.mkdir(parents=True, exist_ok=True)

    images = discover_canonical_images(image_root)
    if len(images) != args.expected_pages:
        raise RuntimeError(
            f"Expected {args.expected_pages} canonical images, found {len(images)}"
        )
    inventory = build_inventory(main_repo, images, args.historical_run_date)
    report = build_report(
        inventory=inventory,
        historical_run_date=args.historical_run_date,
        expected_pages=args.expected_pages,
        preflight_only=args.preflight_only,
    )
    write_report(report_path, report)
    if args.preflight_only:
        print(f"Report: {report_path}")
        return 0

    if not image_exists(worktree):
        raise RuntimeError(
            f"Verified fresh image is missing: {IMAGE_TAG}. "
            "Run run_fresh_upstream_homr_probe.sh with --keep-image first."
        )

    pdfscore_snapshot = output_root / "pdfscore_source_snapshot"
    report["pdfscore_source"] = extract_snapshot(
        worktree,
        PDFSCORE_SOURCE_REF,
        pdfscore_snapshot,
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

    pages: list[dict[str, Any]] = []
    for item in inventory:
        artifact_key = str(item["artifact_key"])
        try:
            page_result = run_page(
                item=item,
                worktree=worktree,
                output_root=output_root,
                mounts=mounts,
                existing=existing_pages.get(artifact_key),
                resume=args.resume,
            )
        except Exception as error:  # pylint: disable=broad-except
            page_result = {
                **item,
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        pages.append(page_result)
        report["pages"] = pages
        report["aggregate"] = aggregate_results(pages)
        write_report(report_path, report)

    aggregate = aggregate_results(pages)
    report["aggregate"] = aggregate
    report["all_semantic_equal"] = (
        aggregate["pages_completed"] == args.expected_pages
        and aggregate["pages_failed"] == 0
        and aggregate["pages_different"] == 0
    )
    report["status"] = "completed" if aggregate["pages_failed"] == 0 else "failed"
    write_report(report_path, report)

    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
