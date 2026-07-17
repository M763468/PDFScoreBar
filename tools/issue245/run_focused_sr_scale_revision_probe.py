#!/usr/bin/env python3
"""Compare focused SR x2/x4 HOMR outputs across current and historical sources.

The probe runs only the two Issue #245 residual pages.  It fixes the external
HOMR runtime to the same revision used by the baseline evaluator probe, varies
only the PDFScoreBar evaluator source and SR scale, and then replays hybrid
consensus plus row-stat construction from saved artifacts.  It does not run
dense candidate generation, filtering, CNN scoring, MMR, or numbering.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue245.prepare_accuracy_first_mixed_route import (
    inventory_by_key,
    load_inventory,
    resolve_repo_path,
)
from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    DEFAULT_HISTORICAL_REF,
    HOMR_COMMIT,
    IMAGE_TAG,
    compare_records,
    ensure_image,
    extract_snapshot,
    git_output,
    load_records,
    run_logged,
    sha256_file,
)

Box = tuple[int, int, int, int]
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_DRIFT_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json"
)
OUTPUT_REL = Path("logs/issue245_accuracy_first_stage_e/focused_sr_scale_revision_probe")
ROW_CLUSTER_MAX_DIST = 25.0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value)  # type: ignore[return-value]


def _normalize_boxes(values: Iterable[Sequence[Any]]) -> list[Box]:
    return [_normalize_box(value) for value in values]


def _unique_pages(report: dict[str, Any]) -> list[dict[str, Any]]:
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    for target in report.get("targets", []):
        if not isinstance(target, dict):
            continue
        score = str(target["score"])
        page = str(target["page"])
        key = (score, page)
        record = pages.setdefault(
            key,
            {
                "score": score,
                "page": page,
                "paths": dict(target["paths"]),
                "references": [],
            },
        )
        reference = list(_normalize_box(target["reference"]))
        if reference not in record["references"]:
            record["references"].append(reference)
    return [pages[key] for key in sorted(pages)]


def _reference_band_present(boxes: Sequence[Box], reference: Box) -> bool:
    expected = (min(reference[1], reference[3]), max(reference[1], reference[3]))
    rows = build_row_stats(
        boxes,
        cluster_max_dist=ROW_CLUSTER_MAX_DIST,
        min_row_count=1,
    )
    return any((int(row["top"]), int(row["bottom"])) == expected for row in rows)


def _variant_consensus_summary(
    *,
    baseline_path: Path,
    omr_path: Path,
    sr_detection_path: Path,
    references: Sequence[Box],
) -> dict[str, Any]:
    baseline = load_json_boxes(baseline_path)
    omr = load_json_boxes(omr_path)
    sr = load_json_boxes(sr_detection_path)
    hybrid = _normalize_boxes(
        apply_hybrid_consensus_filter(
            baseline_boxes=baseline,
            sr_boxes=sr,
            omr_boxes=omr,
        )
    )
    rows = build_row_stats(
        hybrid,
        cluster_max_dist=ROW_CLUSTER_MAX_DIST,
        min_row_count=1,
    )
    return {
        "sr_candidate_count": len(sr),
        "hybrid_candidate_count": len(hybrid),
        "row_count": len(rows),
        "reference_bands": [
            {
                "reference": list(reference),
                "present": _reference_band_present(hybrid, reference),
            }
            for reference in references
        ],
    }


def _classify_target(
    *,
    current_x2_present: bool,
    current_x4_present: bool,
    historical_source_x4_present: bool,
) -> str:
    if not current_x2_present and current_x4_present:
        return "sr_scale_regression_confirmed"
    if not current_x4_present and historical_source_x4_present:
        return "current_evaluator_source_regression"
    if current_x2_present:
        return "saved_current_artifact_or_runtime_mismatch"
    return "unresolved"


def _container_image_path(main_repo: Path, image_path: Path) -> str:
    relative = image_path.resolve().relative_to(main_repo.resolve())
    return str(Path("/workspace") / relative)


def _run_variant(
    *,
    name: str,
    worktree: Path,
    main_repo: Path,
    output_root: Path,
    image_paths: Sequence[Path],
    sr_scale: int,
    snapshot_root: Path | None,
    force: bool,
) -> dict[str, Any]:
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
        f"{main_repo / 'data'}:/workspace/data:ro",
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

    evaluator_args = [
        "--images",
        *[_container_image_path(main_repo, path) for path in image_paths],
        "--output-root",
        str(output_container),
        "--force-run-id",
        run_id,
        "--enable-sr",
        "--enable-segnet-cache",
    ]
    if snapshot_root is None:
        evaluator_args.extend(["--sr-scale", str(sr_scale)])
    elif sr_scale != 4:
        raise ValueError("Historical evaluator source only supports its x4 SR path")

    command = [
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
        *evaluator_args,
    ]
    run_logged(command, output_host / "evaluator.log", cwd=worktree)

    detections: dict[tuple[str, str], Path] = {}
    for image_path in image_paths:
        detection_path = (
            output_host
            / "evaluator"
            / run_id
            / image_path.stem
            / f"{image_path.stem}_detections.json"
        )
        if not detection_path.is_file():
            raise FileNotFoundError(f"Detection was not created: {detection_path}")
        detections[(image_path.parent.name, image_path.stem)] = detection_path

    return {
        "name": name,
        "sr_scale": sr_scale,
        "source_root": str(source_root),
        "run_id": run_id,
        "log": str(output_host / "evaluator.log"),
        "detections": {
            f"{score}/{page}": {
                "path": str(path),
                "sha256": sha256_file(path),
                "count": len(load_records(path)),
            }
            for (score, page), path in sorted(detections.items())
        },
    }


def _resolve_variant_detection(variant: dict[str, Any], score: str, page: str) -> Path:
    raw = variant["detections"][f"{score}/{page}"]["path"]
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--drift-report", type=Path, default=DEFAULT_DRIFT_REPORT)
    parser.add_argument("--historical-ref", default=DEFAULT_HISTORICAL_REF)
    parser.add_argument(
        "--base-image",
        default=os.environ.get("ISSUE245_REVISION_BASE_IMAGE", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--remove-image", action="store_true")
    args = parser.parse_args()

    worktree = Path(git_output(Path.cwd(), "rev-parse", "--show-toplevel"))
    main_repo = args.main_repo_root.expanduser().resolve()
    drift_report_path = args.drift_report.expanduser()
    if not drift_report_path.is_absolute():
        drift_report_path = worktree / drift_report_path
    drift_report = _load_json(drift_report_path)
    pages = _unique_pages(drift_report)
    if len(pages) != 2:
        raise RuntimeError(f"Expected two focused pages, found {len(pages)}")

    historical_inventory_path = resolve_repo_path(main_repo, drift_report["historical_inventory"])
    historical_inventory = load_inventory(historical_inventory_path)
    historical_by_key = inventory_by_key(historical_inventory)

    image_paths: list[Path] = []
    for page in pages:
        key = (page["score"], page["page"])
        image_path = resolve_repo_path(main_repo, historical_by_key[key]["image"])
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        page["image"] = str(image_path)
        page["image_sha256"] = sha256_file(image_path)
        image_paths.append(image_path)

    output_root = main_repo / OUTPUT_REL
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_root = output_root / "historical_source_snapshot"
    snapshot = extract_snapshot(worktree, args.historical_ref, snapshot_root)

    report: dict[str, Any] = {
        "schema_version": "issue245.focused_sr_scale_revision_probe.v1",
        "status": "running",
        "production_default_changed": False,
        "dense_or_cnn_run": False,
        "isolation": {
            "homr_commit": HOMR_COMMIT,
            "image_tag": IMAGE_TAG,
            "historical_ref": args.historical_ref,
            "variable": "PDFScoreBar evaluator source and SR scale",
        },
        "drift_report": str(drift_report_path),
        "historical_inventory": str(historical_inventory_path),
        "historical_source": snapshot,
        "pages": pages,
        "variants": {},
        "targets": [],
    }
    report_path = output_root / "focused_sr_scale_revision_probe_report.json"

    try:
        ensure_image(
            worktree,
            output_root,
            base_image=args.base_image,
            rebuild=args.rebuild,
        )
        for name, sr_scale, snapshot_path in (
            ("current_source_x2", 2, None),
            ("current_source_x4", 4, None),
            ("historical_source_x4", 4, snapshot_root),
        ):
            variant = _run_variant(
                name=name,
                worktree=worktree,
                main_repo=main_repo,
                output_root=output_root,
                image_paths=image_paths,
                sr_scale=sr_scale,
                snapshot_root=snapshot_path,
                force=args.force,
            )
            report["variants"][name] = variant
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        for page in pages:
            score = page["score"]
            page_name = page["page"]
            baseline_path = Path(page["paths"]["fresh_baseline"])
            current_omr_path = Path(page["paths"]["current_omr"])
            saved_current_sr_path = Path(page["paths"]["current_sr"])
            saved_historical_sr_path = Path(page["paths"]["historical_sr"])
            references = [_normalize_box(value) for value in page["references"]]

            variant_summaries: dict[str, Any] = {}
            for name, variant in report["variants"].items():
                detection_path = _resolve_variant_detection(variant, score, page_name)
                summary = _variant_consensus_summary(
                    baseline_path=baseline_path,
                    omr_path=current_omr_path,
                    sr_detection_path=detection_path,
                    references=references,
                )
                summary["comparison_to_saved_current_sr"] = compare_records(
                    load_records(saved_current_sr_path), load_records(detection_path)
                )
                summary["comparison_to_saved_historical_sr"] = compare_records(
                    load_records(saved_historical_sr_path), load_records(detection_path)
                )
                variant_summaries[name] = summary

            page["variant_summaries"] = variant_summaries
            for reference in references:
                presence = {
                    name: next(
                        item["present"]
                        for item in summary["reference_bands"]
                        if item["reference"] == list(reference)
                    )
                    for name, summary in variant_summaries.items()
                }
                report["targets"].append(
                    {
                        "score": score,
                        "page": page_name,
                        "reference": list(reference),
                        "variant_reference_band_present": presence,
                        "classification": _classify_target(
                            current_x2_present=presence["current_source_x2"],
                            current_x4_present=presence["current_source_x4"],
                            historical_source_x4_present=presence["historical_source_x4"],
                        ),
                    }
                )

        report["status"] = "completed"
    except Exception as error:
        report.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    finally:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if args.remove_image:
            subprocess.run(
                ["docker", "image", "rm", IMAGE_TAG],
                cwd=worktree,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    print(f"Report: {report_path}")
    for target in report.get("targets", []):
        print(
            f"{target['score']}/{target['page']} reference={target['reference']} "
            f"classification={target['classification']}"
        )
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
