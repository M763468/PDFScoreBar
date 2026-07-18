#!/usr/bin/env python3
"""Evaluate a selective aligned-expansion rescue for Issue #245.

This focused investigation reuses saved current artifacts. It does not run HOMR,
Real-ESRGAN, OMR, CNN, MMR, numbering, or the full-68 evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2

from src.common import barline_iou
from src.pipeline.steps import probe_scan as probe_scan_module
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue245.run_fresh_row_band_rescue_probe import (
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
DEFAULT_OUTPUT = Path(
    "logs/issue245_accuracy_first_stage_e/aligned_expansion_candidate_probe"
)
TRACE_VARIANT: dict[str, Any] = {
    "band_source": "row_stats",
    "band_row_pad_ratio": 0.25,
    "scan_disable_existing_suppression": True,
}
X_TOLERANCE = 4.0
MIN_EXISTING_VERTICAL_COVERAGE = 0.80
MIN_HEIGHT_RATIO = 1.25
MAX_HEIGHT_RATIO = 2.00


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


def _semantic_delta(control: Iterable[Box], variant: Iterable[Box]) -> dict[str, Any]:
    control_counter = Counter(control)
    variant_counter = Counter(variant)
    added = sorted((variant_counter - control_counter).elements())
    removed = sorted((control_counter - variant_counter).elements())
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "added_examples": [list(box) for box in added[:30]],
        "removed_examples": [list(box) for box in removed[:30]],
    }


def _centres(box: Box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _aligned_expansion_metrics(candidate: Box, existing: Box) -> dict[str, float] | None:
    candidate_h = float(abs(candidate[3] - candidate[1]))
    existing_h = float(abs(existing[3] - existing[1]))
    if candidate_h <= 0 or existing_h <= 0:
        return None
    candidate_cx, _ = _centres(candidate)
    existing_cx, _ = _centres(existing)
    x_distance = abs(candidate_cx - existing_cx)
    if x_distance > X_TOLERANCE:
        return None
    overlap = max(
        0.0,
        min(max(candidate[1], candidate[3]), max(existing[1], existing[3]))
        - max(min(candidate[1], candidate[3]), min(existing[1], existing[3])),
    )
    existing_coverage = overlap / existing_h
    height_ratio = candidate_h / existing_h
    if existing_coverage < MIN_EXISTING_VERTICAL_COVERAGE:
        return None
    if not (MIN_HEIGHT_RATIO <= height_ratio <= MAX_HEIGHT_RATIO):
        return None
    return {
        "x_distance": x_distance,
        "existing_vertical_coverage": existing_coverage,
        "height_ratio": height_ratio,
    }


def _select_aligned_expansions(
    dropped: list[dict[str, Any]], existing_boxes: list[Box]
) -> list[dict[str, Any]]:
    by_existing: dict[Box, list[dict[str, Any]]] = {}
    for item in dropped:
        reasons = [str(reason) for reason in item.get("reasons", [])]
        if reasons != ["low_paper_overlap"]:
            continue
        candidate = _normalize_box(item["bbox"])
        matches: list[tuple[tuple[float, float, float, Box], Box, dict[str, float]]] = []
        for existing in existing_boxes:
            metrics = _aligned_expansion_metrics(candidate, existing)
            if metrics is None:
                continue
            rank = (
                metrics["x_distance"],
                -metrics["existing_vertical_coverage"],
                abs(metrics["height_ratio"] - 1.5),
                existing,
            )
            matches.append((rank, existing, metrics))
        if not matches:
            continue
        _, existing, metrics = min(matches, key=lambda value: value[0])
        by_existing.setdefault(existing, []).append(
            {
                "raw_bbox": candidate,
                "existing_bbox": existing,
                **metrics,
            }
        )

    selected: list[dict[str, Any]] = []
    for existing, items in sorted(by_existing.items()):
        item = min(
            items,
            key=lambda value: (
                float(value["x_distance"]),
                -float(value["existing_vertical_coverage"]),
                abs(float(value["height_ratio"]) - 1.5),
                value["raw_bbox"],
            ),
        )
        selected.append(item)
    return selected


def _run_capture(
    *,
    image_path: Path,
    score: str,
    mixed_hybrid_path: Path,
    mask_dir: Path,
    output_root: Path,
) -> tuple[Path, list[Box], dict[str, Any]]:
    captured: dict[str, Any] = {"raw_detect": [], "heuristic_dropped": []}
    original_detect = probe_scan_module.detect_probe_scan
    original_filter = probe_scan_module.filter_probe_candidates

    def traced_detect(*args: Any, **kwargs: Any) -> list[Box]:
        boxes = _normalise_boxes(original_detect(*args, **kwargs))
        captured["raw_detect"] = boxes
        return boxes

    def traced_filter(*args: Any, **kwargs: Any) -> tuple[list[Box], list[dict[str, Any]]]:
        keep, dropped = original_filter(*args, **kwargs)
        captured["heuristic_dropped"] = [
            {
                "bbox": list(_normalize_box(item["bbox"])),
                "reasons": [str(reason) for reason in item.get("reasons", [])],
            }
            for item in dropped
        ]
        return keep, dropped

    probe_scan_module.detect_probe_scan = traced_detect
    probe_scan_module.filter_probe_candidates = traced_filter
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
    return output_path, final_boxes, captured


def _classify_target(matches: dict[str, dict[str, Any]]) -> str:
    if matches["current_final"]["accepted"]:
        return "already_present_in_current_final"
    if matches["aligned_trimmed_additive"]["accepted"]:
        return "restored_by_aligned_trimmed_additive"
    if matches["aligned_raw_additive"]["accepted"]:
        return "restored_by_preserving_aligned_raw_expansion"
    return "unresolved"


def _write_boxes(path: Path, boxes: Iterable[Box]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([list(box) for box in sorted(set(boxes))], indent=2), encoding="utf-8")


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
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)

        page_root = output_root / score / page
        output_path, current_final, captured = _run_capture(
            image_path=image_path,
            score=score,
            mixed_hybrid_path=mixed_hybrid_path,
            mask_dir=current_sr_path.parent,
            output_root=page_root / "current",
        )
        existing_boxes = _normalise_boxes(load_json_boxes(mixed_hybrid_path))
        selected = _select_aligned_expansions(captured["heuristic_dropped"], existing_boxes)
        min_height_px = int(image.shape[0] * 0.006)
        min_width_px = 0
        for item in selected:
            raw = item["raw_bbox"]
            trimmed = _normalize_box(
                probe_scan_module.trim_box_to_ink(image, raw, ink_threshold=240)
            )
            item["trimmed_bbox"] = trimmed
            item["trimmed_passes_size"] = (
                abs(trimmed[3] - trimmed[1]) >= min_height_px
                and abs(trimmed[2] - trimmed[0]) >= min_width_px
            )
            item["trimmed_exact_existing"] = trimmed in set(existing_boxes)
            item["trimmed_existing_match"] = _best_match(trimmed, existing_boxes)

        trimmed_additions = [
            item["trimmed_bbox"] for item in selected if item["trimmed_passes_size"]
        ]
        raw_additions = [item["raw_bbox"] for item in selected]
        variants: dict[str, list[Box]] = {
            "current_final": sorted(set(current_final)),
            "aligned_trimmed_additive": sorted(set(current_final) | set(trimmed_additions)),
            "aligned_raw_additive": sorted(set(current_final) | set(raw_additions)),
        }
        variant_paths: dict[str, str] = {}
        for name, boxes in variants.items():
            path = page_root / name / "pipeline2_no_peak_candidates.json"
            _write_boxes(path, boxes)
            variant_paths[name] = str(path)

        for target in [item for item in TARGETS if item["score"] == score and item["page"] == page]:
            reference = _normalize_box(target["reference"])
            matches = {name: _best_match(reference, boxes) for name, boxes in variants.items()}
            selected_matches = []
            for item in selected:
                raw_match = float(barline_iou(reference, item["raw_bbox"]))
                trimmed_match = float(barline_iou(reference, item["trimmed_bbox"]))
                if max(raw_match, trimmed_match) <= 0:
                    continue
                selected_matches.append(
                    {
                        "raw_bbox": list(item["raw_bbox"]),
                        "raw_iou": raw_match,
                        "trimmed_bbox": list(item["trimmed_bbox"]),
                        "trimmed_iou": trimmed_match,
                        "existing_bbox": list(item["existing_bbox"]),
                        "existing_iou": float(barline_iou(reference, item["existing_bbox"])),
                        "height_ratio": item["height_ratio"],
                        "existing_vertical_coverage": item["existing_vertical_coverage"],
                        "x_distance": item["x_distance"],
                        "trimmed_exact_existing": item["trimmed_exact_existing"],
                    }
                )
            selected_matches.sort(key=lambda value: (-value["raw_iou"], value["raw_bbox"]))
            target_results.append(
                {
                    "score": score,
                    "page": page,
                    "reference": list(reference),
                    "variant_matches": matches,
                    "selected_expansion_matches": selected_matches[:10],
                    "classification": _classify_target(matches),
                }
            )

        current_set = set(variants["current_final"])
        selected_serializable = [
            {
                **{
                    key: list(value) if isinstance(value, tuple) else value
                    for key, value in item.items()
                    if key != "trimmed_existing_match"
                },
                "trimmed_existing_match": item["trimmed_existing_match"],
            }
            for item in selected
        ]
        pages.append(
            {
                "score": score,
                "page": page,
                "image": str(image_path),
                "mixed_hybrid": str(mixed_hybrid_path),
                "current_output": str(output_path),
                "raw_detect_count": len(captured["raw_detect"]),
                "heuristic_dropped_count": len(captured["heuristic_dropped"]),
                "existing_box_count": len(existing_boxes),
                "selected_expansion_count": len(selected),
                "selected_expansions": selected_serializable,
                "variants": {
                    name: {
                        "output": variant_paths[name],
                        "candidate_count": len(boxes),
                        "delta_from_current": _semantic_delta(current_set, boxes),
                    }
                    for name, boxes in variants.items()
                },
            }
        )

    return {
        "schema_version": "issue245.aligned_expansion_candidate_probe.v1",
        "status": "completed",
        "production_default_changed": False,
        "upstream_inference_run": False,
        "cnn_or_mmr_run": False,
        "drift_report": str(drift_report_path),
        "trace_variant": TRACE_VARIANT,
        "selection_contract": {
            "sole_drop_reason": "low_paper_overlap",
            "x_tolerance": X_TOLERANCE,
            "min_existing_vertical_coverage": MIN_EXISTING_VERTICAL_COVERAGE,
            "min_height_ratio": MIN_HEIGHT_RATIO,
            "max_height_ratio": MAX_HEIGHT_RATIO,
            "max_one_candidate_per_existing_box": True,
        },
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
    report_path = output_root / "aligned_expansion_candidate_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
