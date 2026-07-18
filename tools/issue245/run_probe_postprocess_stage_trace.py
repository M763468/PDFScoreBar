#!/usr/bin/env python3
"""Trace focused Issue #245 probe candidates through post-processing stages.

This investigation reuses saved current artifacts. It does not run HOMR,
Real-ESRGAN, OMR, CNN, MMR, numbering, or the full-68 evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2

from src.common import barline_iou
from src.pipeline.steps import probe_scan as probe_scan_module
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue245.run_fresh_row_band_rescue_probe import (
    PRODUCTION_FILTER_KWARGS,
    TARGETS,
    _find_page_record,
    _load_json,
    _normalize_box,
    _resolve_artifact,
    _resolve_input,
    _run_page_variant,
)

Box = tuple[int, int, int, int]
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_DRIFT_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json"
)
DEFAULT_OUTPUT = Path("logs/issue245_accuracy_first_stage_e/probe_postprocess_stage_trace")
TRACE_VARIANT: dict[str, Any] = {
    "band_source": "row_stats",
    "band_row_pad_ratio": 0.25,
    "scan_disable_existing_suppression": True,
}


def _normalise_boxes(values: Iterable[Sequence[Any]]) -> list[Box]:
    return [_normalize_box(value) for value in values]


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


def _contains_exact(boxes: Iterable[Box], target: Box | None) -> bool:
    return target is not None and target in set(boxes)


def _drop_reasons(dropped: list[dict[str, Any]], target: Box) -> list[str]:
    for item in dropped:
        bbox = item.get("bbox")
        if bbox is not None and _normalize_box(bbox) == target:
            return [str(reason) for reason in item.get("reasons", [])]
    return []


def _trimmed_box(trim_calls: list[dict[str, Box]], target: Box) -> Box | None:
    for item in trim_calls:
        if item["before"] == target:
            return item["after"]
    return None


def _classify_target_trace(trace: dict[str, Any]) -> str:
    raw = trace["raw_detect"]
    if not raw["accepted"]:
        return "raw_probe_candidate_not_restored"
    if not trace["present_after_initial_size_filter"]:
        return "dropped_by_initial_size_filter"
    if trace["heuristic_drop_reasons"]:
        return "dropped_by_heuristic_filter"
    if not trace["present_after_heuristic_filter"]:
        return "missing_after_heuristic_filter"
    if trace["trimmed_bbox"] is None:
        return "trim_not_observed"
    if raw["accepted"] and not trace["trimmed_match"]["accepted"]:
        if trace["trimmed_exact_existing"]:
            return "trim_collapsed_to_existing_short_box"
        return "trim_geometry_collapse"
    if not trace["present_after_post_trim_size_filter"]:
        return "dropped_by_post_trim_size_filter"
    if not trace["trimmed_exact_in_final"]:
        return "lost_during_final_set_merge"
    return "restored_in_final_output"


def _trace_target(
    *,
    reference: Box,
    captured: dict[str, Any],
    existing_boxes: list[Box],
    final_boxes: list[Box],
) -> dict[str, Any]:
    raw_match = _best_match(reference, captured["raw_detect"])
    raw_bbox = (
        _normalize_box(raw_match["best_bbox"]) if raw_match["best_bbox"] is not None else None
    )
    if raw_bbox is None:
        result = {
            "reference": list(reference),
            "raw_detect": raw_match,
            "present_after_initial_size_filter": False,
            "present_after_heuristic_filter": False,
            "heuristic_drop_reasons": [],
            "trimmed_bbox": None,
            "trimmed_match": _best_match(reference, []),
            "present_after_post_trim_size_filter": False,
            "trimmed_exact_existing": False,
            "trimmed_existing_best": _best_match(reference, existing_boxes),
            "trimmed_exact_in_final": False,
            "final_match": _best_match(reference, final_boxes),
        }
        result["classification"] = _classify_target_trace(result)
        return result

    trimmed = _trimmed_box(captured["trim_calls"], raw_bbox)
    result = {
        "reference": list(reference),
        "raw_detect": raw_match,
        "raw_bbox": list(raw_bbox),
        "present_after_initial_size_filter": _contains_exact(
            captured["initial_size_keep"], raw_bbox
        ),
        "present_after_heuristic_filter": _contains_exact(captured["heuristic_keep"], raw_bbox),
        "heuristic_drop_reasons": _drop_reasons(captured["heuristic_dropped"], raw_bbox),
        "trimmed_bbox": list(trimmed) if trimmed is not None else None,
        "trimmed_match": _best_match(reference, [trimmed] if trimmed is not None else []),
        "present_after_post_trim_size_filter": _contains_exact(
            captured["post_trim_size_keep"], trimmed
        ),
        "trimmed_exact_existing": _contains_exact(existing_boxes, trimmed),
        "trimmed_existing_best": _best_match(trimmed, existing_boxes)
        if trimmed is not None
        else _best_match(reference, existing_boxes),
        "trimmed_exact_in_final": _contains_exact(final_boxes, trimmed),
        "final_match": _best_match(reference, final_boxes),
    }
    result["classification"] = _classify_target_trace(result)
    return result


def _run_traced_page(
    *,
    image_path: Path,
    score: str,
    mixed_hybrid_path: Path,
    mask_dir: Path,
    output_root: Path,
) -> tuple[Path, list[Box], dict[str, Any]]:
    captured: dict[str, Any] = {
        "raw_detect": [],
        "initial_size_keep": [],
        "heuristic_keep": [],
        "heuristic_dropped": [],
        "trim_calls": [],
        "post_trim_size_keep": [],
    }

    original_detect = probe_scan_module.detect_probe_scan
    original_filter = probe_scan_module.filter_probe_candidates
    original_trim = probe_scan_module.trim_box_to_ink

    def traced_detect(*args: Any, **kwargs: Any) -> list[Box]:
        boxes = _normalise_boxes(original_detect(*args, **kwargs))
        captured["raw_detect"] = boxes
        return boxes

    def traced_filter(*args: Any, **kwargs: Any) -> tuple[list[Box], list[dict[str, Any]]]:
        candidates = kwargs.get("candidates")
        if candidates is None and args:
            candidates = args[0]
        captured["initial_size_keep"] = _normalise_boxes(candidates or [])
        keep, dropped = original_filter(*args, **kwargs)
        captured["heuristic_keep"] = _normalise_boxes(keep)
        captured["heuristic_dropped"] = [
            {
                "bbox": list(_normalize_box(item["bbox"])),
                "reasons": [str(reason) for reason in item.get("reasons", [])],
            }
            for item in dropped
        ]
        return keep, dropped

    def traced_trim(*args: Any, **kwargs: Any) -> Box:
        box_value = kwargs.get("box")
        if box_value is None and len(args) >= 2:
            box_value = args[1]
        before = _normalize_box(box_value)
        after = _normalize_box(original_trim(*args, **kwargs))
        captured["trim_calls"].append({"before": before, "after": after})
        return after

    probe_scan_module.detect_probe_scan = traced_detect
    probe_scan_module.filter_probe_candidates = traced_filter
    probe_scan_module.trim_box_to_ink = traced_trim
    try:
        output_path, final_boxes = _run_page_variant(
            image_path=image_path,
            score=score,
            mixed_hybrid_path=mixed_hybrid_path,
            mask_dir=mask_dir,
            output_root=output_root,
            variant_kwargs=dict(TRACE_VARIANT),
        )
    finally:
        probe_scan_module.detect_probe_scan = original_detect
        probe_scan_module.filter_probe_candidates = original_filter
        probe_scan_module.trim_box_to_ink = original_trim

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    min_height_px = int(image.shape[0] * 0.006)
    min_width_px = 0
    captured["post_trim_size_keep"] = [
        item["after"]
        for item in captured["trim_calls"]
        if abs(item["after"][3] - item["after"][1]) >= min_height_px
        and abs(item["after"][2] - item["after"][0]) >= min_width_px
    ]
    captured["stage_counts"] = {
        "raw_detect": len(captured["raw_detect"]),
        "initial_size_keep": len(captured["initial_size_keep"]),
        "heuristic_keep": len(captured["heuristic_keep"]),
        "heuristic_dropped": len(captured["heuristic_dropped"]),
        "trim_calls": len(captured["trim_calls"]),
        "post_trim_size_keep": len(captured["post_trim_size_keep"]),
        "final_output": len(final_boxes),
    }
    captured["min_height_px"] = min_height_px
    captured["min_width_px"] = min_width_px
    return output_path, final_boxes, captured


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

        page_root = output_root / score / page
        output_path, final_boxes, captured = _run_traced_page(
            image_path=image_path,
            score=score,
            mixed_hybrid_path=mixed_hybrid_path,
            mask_dir=current_sr_path.parent,
            output_root=page_root,
        )
        existing_boxes = _normalise_boxes(load_json_boxes(mixed_hybrid_path))
        page_targets = [item for item in TARGETS if item["score"] == score and item["page"] == page]
        for target in page_targets:
            target_results.append(
                {
                    "score": score,
                    "page": page,
                    **_trace_target(
                        reference=_normalize_box(target["reference"]),
                        captured=captured,
                        existing_boxes=existing_boxes,
                        final_boxes=final_boxes,
                    ),
                }
            )

        pages.append(
            {
                "score": score,
                "page": page,
                "image": str(image_path),
                "mixed_hybrid": str(mixed_hybrid_path),
                "output": str(output_path),
                "existing_box_count": len(existing_boxes),
                "stage_counts": captured["stage_counts"],
                "min_height_px": captured["min_height_px"],
                "min_width_px": captured["min_width_px"],
                "heuristic_drop_reason_counts": {
                    reason: sum(
                        1 for item in captured["heuristic_dropped"] if reason in item["reasons"]
                    )
                    for reason in sorted(
                        {
                            reason
                            for item in captured["heuristic_dropped"]
                            for reason in item["reasons"]
                        }
                    )
                },
            }
        )

    return {
        "schema_version": "issue245.probe_postprocess_stage_trace.v1",
        "status": "completed",
        "production_default_changed": False,
        "upstream_inference_run": False,
        "cnn_or_mmr_run": False,
        "drift_report": str(drift_report_path),
        "variant": TRACE_VARIANT,
        "filter_settings": PRODUCTION_FILTER_KWARGS,
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
    report_path = output_root / "probe_postprocess_stage_trace_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
