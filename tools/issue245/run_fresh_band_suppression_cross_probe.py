#!/usr/bin/env python3
"""Cross row-band padding with existing-box suppression for Issue #245.

This focused investigation reuses saved current artifacts. It does not run
HOMR, Real-ESRGAN, OMR, CNN, MMR, numbering, or the full-68 evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue245.run_fresh_row_band_rescue_probe import (
    PRODUCTION_FILTER_KWARGS,
    PRODUCTION_PROBE_KWARGS,
    TARGETS,
    _find_page_record,
    _load_json,
    _normalize_box,
    _resolve_artifact,
    _resolve_input,
    _run_page_variant,
    _semantic_delta,
)

Box = tuple[int, int, int, int]
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_DRIFT_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json"
)
DEFAULT_OUTPUT = Path("logs/issue245_accuracy_first_stage_e/fresh_band_suppression_cross_probe")

VARIANTS: dict[str, dict[str, Any]] = {
    "row_stats_control": {"band_source": "row_stats"},
    "pad025_iou050": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.25,
        "scan_existing_min_vertical_iou": 0.50,
    },
    "pad050_iou050": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.50,
        "scan_existing_min_vertical_iou": 0.50,
    },
    "pad050_iou075": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.50,
        "scan_existing_min_vertical_iou": 0.75,
    },
    "pad075_iou050": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.75,
        "scan_existing_min_vertical_iou": 0.50,
    },
    "pad075_iou075": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.75,
        "scan_existing_min_vertical_iou": 0.75,
    },
    "pad025_no_suppress": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.25,
        "scan_disable_existing_suppression": True,
    },
    "pad050_no_suppress": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.50,
        "scan_disable_existing_suppression": True,
    },
    "pad075_no_suppress": {
        "band_source": "row_stats",
        "band_row_pad_ratio": 0.75,
        "scan_disable_existing_suppression": True,
    },
}


def _best_match(reference: Box, candidates: Iterable[Box]) -> dict[str, Any]:
    ranked = sorted(
        ((candidate, float(barline_iou(reference, candidate))) for candidate in candidates),
        key=lambda item: (-item[1], item[0]),
    )
    best_box, best_iou = ranked[0] if ranked else (None, 0.0)
    return {
        "accepted": best_iou > 0.5,
        "max_iou": best_iou,
        "best_bbox": list(best_box) if best_box is not None else None,
    }


def _debug_json(debug_png: Path) -> Path:
    return debug_png.with_suffix(".json")


def _accepted_status(status: str) -> bool:
    return status == "accepted" or status.startswith("accepted_")


def _record_candidate(record: dict[str, Any], probe_width: int = 4) -> Box | None:
    col = record.get("col")
    band = record.get("band")
    if col is None or not isinstance(band, list) or len(band) != 2:
        return None
    x = int(round(float(col)))
    half = max(1, int(round(probe_width / 2)))
    return (x - half, int(band[0]), x + half, int(band[1]))


def _target_debug_summary(
    debug_payload: dict[str, Any], reference: Box, *, x_tolerance: int = 14
) -> dict[str, Any]:
    cx = (reference[0] + reference[2]) / 2.0
    selected: list[dict[str, Any]] = []
    raw_matches: list[tuple[Box, float, str]] = []
    for record in debug_payload.get("records", []):
        if not isinstance(record, dict) or record.get("col") is None:
            continue
        col = float(record["col"])
        if abs(col - cx) > x_tolerance:
            continue
        compact = {
            "status": str(record.get("status", "")),
            "col": col,
            "ratio": record.get("ratio"),
            "band": record.get("band"),
            "staff_band": record.get("staff_band"),
            "pred_band": record.get("pred_band"),
            "seed_col": record.get("seed_col"),
        }
        selected.append(compact)
        candidate = _record_candidate(record)
        if candidate is not None and _accepted_status(compact["status"]):
            raw_matches.append(
                (candidate, float(barline_iou(reference, candidate)), compact["status"])
            )

    selected.sort(key=lambda item: (abs(float(item["col"]) - cx), item["status"]))
    raw_matches.sort(key=lambda item: (-item[1], item[0]))
    best = raw_matches[0] if raw_matches else None
    statuses = sorted({item["status"] for item in selected})
    return {
        "statuses": statuses,
        "records": selected[:20],
        "raw_accepted": bool(raw_matches),
        "raw_max_iou": best[1] if best else 0.0,
        "raw_best_bbox": list(best[0]) if best else None,
        "raw_best_status": best[2] if best else None,
    }


def _classify_target(
    final_matches: dict[str, dict[str, Any]],
    debug_matches: dict[str, dict[str, Any]],
) -> str:
    if final_matches["row_stats_control"]["accepted"]:
        return "already_present_in_control"
    for name in final_matches:
        if name == "row_stats_control":
            continue
        if final_matches[name]["accepted"]:
            return f"restored_by_{name}"
    if any(item["raw_max_iou"] > 0.5 for item in debug_matches.values()):
        return "raw_candidate_lost_after_probe_scan"
    statuses = {status for item in debug_matches.values() for status in item["statuses"]}
    if statuses and statuses <= {"existing"}:
        return "still_existing_suppressed"
    if "existing" in statuses:
        return "existing_suppression_mixed_with_other_rejection"
    if statuses:
        return "probe_scan_rejected_before_existing_suppression"
    return "no_target_peak_record"


def _serializable_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value for key, value in settings.items()
    }


def build_report(*, main_repo: Path, drift_report_path: Path, output_root: Path) -> dict[str, Any]:
    drift_report = _load_json(drift_report_path)
    page_keys = sorted({(str(item["score"]), str(item["page"])) for item in TARGETS})
    pages: list[dict[str, Any]] = []
    target_results: list[dict[str, Any]] = []

    for score, page in page_keys:
        record = _find_page_record(drift_report, score, page)
        paths = record.get("paths", {})
        current_sr_path = _resolve_artifact(str(paths["current_sr"]), main_repo=main_repo)
        mixed_hybrid_path = _resolve_artifact(str(paths["mixed_hybrid"]), main_repo=main_repo)
        image_path = (
            main_repo / "data" / "evaluation2" / "images" / score / f"{page}.png"
        ).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        mask_dir = current_sr_path.parent

        variants: dict[str, dict[str, Any]] = {}
        variant_boxes: dict[str, list[Box]] = {}
        variant_debug: dict[str, dict[str, Any]] = {}
        page_root = output_root / score / page
        for variant_name, public_settings in VARIANTS.items():
            variant_root = page_root / variant_name
            debug_png = variant_root / "probe_debug.png"
            runtime_settings = dict(public_settings)
            runtime_settings["debug_path"] = debug_png
            output_path, boxes = _run_page_variant(
                image_path=image_path,
                score=score,
                mixed_hybrid_path=mixed_hybrid_path,
                mask_dir=mask_dir,
                output_root=variant_root,
                variant_kwargs=runtime_settings,
            )
            debug_path = _debug_json(debug_png)
            if not debug_path.is_file():
                raise FileNotFoundError(debug_path)
            debug_payload = _load_json(debug_path)
            variant_boxes[variant_name] = boxes
            variant_debug[variant_name] = debug_payload
            variants[variant_name] = {
                "settings": _serializable_settings(public_settings),
                "output": str(output_path),
                "debug_json": str(debug_path),
                "candidate_count": len(boxes),
            }

        control_boxes = variant_boxes["row_stats_control"]
        for variant_name, boxes in variant_boxes.items():
            variants[variant_name]["delta_from_control"] = _semantic_delta(control_boxes, boxes)

        page_targets = [item for item in TARGETS if item["score"] == score and item["page"] == page]
        for target in page_targets:
            reference = _normalize_box(target["reference"])
            final_matches = {
                name: _best_match(reference, boxes) for name, boxes in variant_boxes.items()
            }
            debug_matches = {
                name: _target_debug_summary(payload, reference)
                for name, payload in variant_debug.items()
            }
            target_results.append(
                {
                    "score": score,
                    "page": page,
                    "reference": list(reference),
                    "final_matches": final_matches,
                    "debug_matches": debug_matches,
                    "classification": _classify_target(final_matches, debug_matches),
                }
            )

        pages.append(
            {
                "score": score,
                "page": page,
                "image": str(image_path),
                "current_sr": str(current_sr_path),
                "mixed_hybrid": str(mixed_hybrid_path),
                "existing_box_count": len(load_json_boxes(mixed_hybrid_path)),
                "variants": variants,
            }
        )

    return {
        "schema_version": "issue245.fresh_band_suppression_cross_probe.v1",
        "status": "completed",
        "production_default_changed": False,
        "upstream_inference_run": False,
        "cnn_or_mmr_run": False,
        "drift_report": str(drift_report_path),
        "production_probe_settings": {
            "probe": PRODUCTION_PROBE_KWARGS,
            "filter": PRODUCTION_FILTER_KWARGS,
        },
        "variants": VARIANTS,
        "pages": pages,
        "targets": target_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--drift-report", type=Path, default=DEFAULT_DRIFT_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main_repo = args.main_repo.expanduser().resolve()
    drift_report_path = _resolve_input(args.drift_report, main_repo=main_repo)
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    report = build_report(
        main_repo=main_repo,
        drift_report_path=drift_report_path,
        output_root=output_root,
    )
    report_path = output_root / "fresh_band_suppression_cross_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
