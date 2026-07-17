#!/usr/bin/env python3
"""Trace saved Issue #245 mixed-hybrid candidates back to their source layers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common import barline_iou
from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)

Box = tuple[int, int, int, int]
CONSENSUS_IOU_THRESHOLD = 0.5


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value)  # type: ignore[return-value]


def _resolve_path(value: str | Path, main_repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return main_repo_root.joinpath(*path.parts[2:])
    if path.is_absolute():
        return path
    return main_repo_root / path


def _find_record(records: Iterable[dict[str, Any]], score: str, page: str) -> dict[str, Any]:
    matches = [
        record
        for record in records
        if str(record.get("score")) == score and str(record.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one record for {score}/{page}, got {len(matches)}")
    return matches[0]


def _find_historical_baseline(run_dir: Path, page: str) -> Path:
    baseline_root = run_dir / "baseline"
    candidates = sorted(baseline_root.rglob(f"{page}_detections.json"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No historical baseline detection JSON below {baseline_root}")
    raise RuntimeError(
        f"Ambiguous historical baseline detection JSON below {baseline_root}: "
        + ", ".join(str(path) for path in candidates)
    )


def _height(box: Box) -> int:
    return abs(box[3] - box[1])


def _l1_distance(left: Box, right: Box) -> int:
    return sum(abs(left[index] - right[index]) for index in range(4))


def _closest_comparison(boxes: Iterable[Box], reference: Box) -> dict[str, Any]:
    box_list = list(boxes)
    if not box_list:
        return {
            "exact_present": False,
            "closest_bbox": None,
            "bbox_delta": None,
            "xdist": None,
            "vertical_overlap": None,
            "reference_height": _height(reference),
            "closest_height": None,
            "height_ratio": None,
            "top_delta": None,
            "bottom_delta": None,
            "center_anchor_matches": [],
        }
    closest = min(
        box_list,
        key=lambda box: (
            center_distance_x(box, reference),
            -barline_vertical_overlap(box, reference),
            _l1_distance(box, reference),
            box,
        ),
    )
    matches = [
        list(box)
        for box in box_list
        if is_barline_match(
            box,
            reference,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
    ]
    closest_height = _height(closest)
    reference_height = _height(reference)
    return {
        "exact_present": reference in box_list,
        "closest_bbox": list(closest),
        "bbox_delta": [closest[index] - reference[index] for index in range(4)],
        "xdist": center_distance_x(closest, reference),
        "vertical_overlap": barline_vertical_overlap(closest, reference),
        "reference_height": reference_height,
        "closest_height": closest_height,
        "height_ratio": closest_height / reference_height if reference_height else None,
        "top_delta": closest[1] - reference[1],
        "bottom_delta": closest[3] - reference[3],
        "center_anchor_matches": matches,
    }


def _support_summary(
    candidate: Box, support_boxes: Iterable[Box], source_path: Path
) -> dict[str, Any]:
    ious = [(box, barline_iou(candidate, box)) for box in support_boxes]
    supporting = [
        {"bbox": list(box), "iou": iou} for box, iou in ious if iou > CONSENSUS_IOU_THRESHOLD
    ]
    return {
        "path": str(source_path),
        "supporting_boxes": supporting,
        "max_iou": max((iou for _, iou in ious), default=0.0),
        "accepted_by_source": bool(supporting),
    }


def _semantic_difference(left: Iterable[Box], right: Iterable[Box]) -> dict[str, Any]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    return {
        "semantic_equal": left_counter == right_counter,
        "left_only": [list(box) for box in sorted((left_counter - right_counter).elements())],
        "right_only": [list(box) for box in sorted((right_counter - left_counter).elements())],
    }


def _classify(
    reference: Box,
    fresh_comparison: dict[str, Any],
    regenerated_mixed: Iterable[Box],
    fresh_baseline: Iterable[Box],
    sr_boxes: Iterable[Box],
    omr_boxes: Iterable[Box],
) -> str:
    fresh_list = list(fresh_baseline)
    if reference in fresh_list:
        return "unresolved" if reference in set(regenerated_mixed) else "current_support_loss"

    matching = [
        _normalize_box(box)
        for box in fresh_comparison["center_anchor_matches"]
        if isinstance(box, list)
    ]
    if matching:
        closest_matching = min(
            matching,
            key=lambda box: (
                center_distance_x(box, reference),
                -barline_vertical_overlap(box, reference),
                _l1_distance(box, reference),
                box,
            ),
        )
        supported = any(
            barline_iou(closest_matching, support) > CONSENSUS_IOU_THRESHOLD
            for support in [*sr_boxes, *omr_boxes]
        )
        if not supported:
            return "fresh_baseline_and_support_loss"
    return "fresh_baseline_geometry_loss"


def _parse_target(raw: str) -> dict[str, Any]:
    parts = raw.split("|")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("target must be score|page|reference_bbox|short_bbox")
    try:
        return {
            "score": parts[0],
            "page": parts[1],
            "reference": _normalize_box(parts[2].split(",")),
            "short": _normalize_box(parts[3].split(",")),
        }
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_report(
    *, main_repo_root: Path, mixed_route_root: Path, targets: list[dict[str, Any]]
) -> dict[str, Any]:
    report_path = mixed_route_root / "accuracy_first_mixed_route_report.json"
    mixed_route_report = _load_json(report_path)
    page_records = mixed_route_report.get("pages", [])
    if not isinstance(page_records, list):
        raise ValueError("Mixed route report pages must be a list")
    historical_inventory_info = mixed_route_report.get("historical_inventory", {})
    if not isinstance(historical_inventory_info, dict) or not historical_inventory_info.get("path"):
        raise ValueError("Mixed route report does not provide historical_inventory.path")
    historical_inventory_path = _resolve_path(historical_inventory_info["path"], main_repo_root)
    historical_inventory = _load_json(historical_inventory_path)
    historical_records = historical_inventory.get("records", [])
    if not isinstance(historical_records, list):
        raise ValueError("Historical inventory records must be a list")

    page_cache: dict[tuple[str, str], dict[str, Any]] = {}
    target_reports = []
    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        reference = _normalize_box(target["reference"])
        short = _normalize_box(target["short"])
        page_record = _find_record(page_records, score, page)
        historical_record = _find_record(historical_records, score, page)

        paths = {
            "fresh_baseline": _resolve_path(page_record["fresh_baseline"], main_repo_root),
            "current_sr": _resolve_path(page_record["current_sr"], main_repo_root),
            "current_omr": _resolve_path(page_record["current_omr"], main_repo_root),
            "mixed_hybrid": _resolve_path(page_record["mixed_hybrid"], main_repo_root),
            "historical_baseline": _find_historical_baseline(
                _resolve_path(historical_record["run_dir"], main_repo_root), page
            ),
            "historical_hybrid": _resolve_path(
                historical_record["hybrid_predictions"], main_repo_root
            ),
        }
        boxes = {name: load_json_boxes(path) for name, path in paths.items()}
        regenerated = [
            _normalize_box(box)
            for box in apply_hybrid_consensus_filter(
                baseline_boxes=boxes["fresh_baseline"],
                sr_boxes=boxes["current_sr"],
                omr_boxes=boxes["current_omr"],
                iou_thresh=CONSENSUS_IOU_THRESHOLD,
            )
        ]
        saved_mixed = boxes["mixed_hybrid"]
        page_key = (score, page)
        if page_key not in page_cache:
            page_cache[page_key] = {
                "score": score,
                "page": page,
                "paths": {name: str(path) for name, path in paths.items()},
                "generated_count": len(regenerated),
                "saved_count": len(saved_mixed),
                **_semantic_difference(regenerated, saved_mixed),
            }

        fresh_comparison = _closest_comparison(boxes["fresh_baseline"], reference)
        historical_comparison = _closest_comparison(boxes["historical_baseline"], reference)
        reference_sr = _support_summary(reference, boxes["current_sr"], paths["current_sr"])
        reference_omr = _support_summary(reference, boxes["current_omr"], paths["current_omr"])
        short_sr = _support_summary(short, boxes["current_sr"], paths["current_sr"])
        short_omr = _support_summary(short, boxes["current_omr"], paths["current_omr"])
        short_in_fresh = short in boxes["fresh_baseline"]
        target_reports.append(
            {
                "score": score,
                "page": page,
                "historical_reference": {
                    "bbox": list(reference),
                    "historical_baseline_exact": reference in boxes["historical_baseline"],
                    "historical_hybrid_exact": reference in boxes["historical_hybrid"],
                },
                "fresh_baseline_comparison": {
                    "path": str(paths["fresh_baseline"]),
                    **fresh_comparison,
                    "accepted_by_regenerated_consensus": reference in regenerated,
                },
                "historical_baseline_comparison": {
                    "path": str(paths["historical_baseline"]),
                    **historical_comparison,
                },
                "current_sr_support": reference_sr,
                "current_omr_support": reference_omr,
                "mixed_short_candidate": {
                    "bbox": list(short),
                    "fresh_baseline_exact": short_in_fresh,
                    "historical_baseline_exact": short in boxes["historical_baseline"],
                    "current_sr_support": short_sr,
                    "current_omr_support": short_omr,
                    "accepted_by_regenerated_consensus": short in regenerated,
                    "present_in_saved_mixed": short in saved_mixed,
                },
                "cause_classification": _classify(
                    reference,
                    fresh_comparison,
                    regenerated,
                    boxes["fresh_baseline"],
                    boxes["current_sr"],
                    boxes["current_omr"],
                ),
                "evidence": {
                    "fresh_baseline_geometry_loss": reference not in boxes["fresh_baseline"],
                    "reference_supported_by_current_sources": (
                        reference_sr["accepted_by_source"] or reference_omr["accepted_by_source"]
                    ),
                    "short_is_fresh_baseline_candidate": short_in_fresh,
                    "short_is_saved_mixed_candidate": short in saved_mixed,
                },
            }
        )

    return {
        "schema_version": "issue245.mixed_hybrid_source_trace.v1",
        "inputs": {
            "main_repo_root": str(main_repo_root),
            "mixed_route_report": str(report_path),
            "historical_inventory": str(historical_inventory_path),
        },
        "consensus_contract": {
            "implementation": "src.pipeline.steps.hybrid_consensus.apply_hybrid_consensus_filter",
            "support_predicate": "barline_iou(candidate, support_box) > 0.5",
            "iou_threshold": CONSENSUS_IOU_THRESHOLD,
        },
        "page_reproduction": list(page_cache.values()),
        "targets": target_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-repo-root", type=Path, required=True)
    parser.add_argument("--mixed-route-root", type=Path, required=True)
    parser.add_argument("--target", type=_parse_target, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        main_repo_root=args.main_repo_root,
        mixed_route_root=args.mixed_route_root,
        targets=args.target,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    mismatches = [page for page in report["page_reproduction"] if not page["semantic_equal"]]
    if mismatches:
        print(f"Saved consensus reproduction mismatch for {len(mismatches)} page(s): {args.output}")
        return 2
    print(f"Saved consensus reproduction matches: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
