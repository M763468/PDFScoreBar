#!/usr/bin/env python3
"""Trace focused detector false negatives through saved Issue #245 artifacts.

The tool only reads existing JSON/image artifacts. It does not run HOMR, SR,
OMR-DLN, dense candidate generation, CNN inference, or the full pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    get_barline_match_rank,
    is_barline_match,
)
from tools.issue120.eval_full68_from_intermediates import PageRecord, find_page_file

Box = tuple[int, int, int, int]
STAGE_ORDER = (
    "mixed_hybrid_input",
    "raw_dense_candidates",
    "filtered_dense_candidates",
    "probe_rescue_candidates",
    "final_candidates",
)
CANDIDATE_FILENAME = "pipeline2_no_peak_candidates.json"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _extract_boxes(payload: Any) -> list[Box]:
    records = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []

    boxes: list[Box] = []
    for item in records:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            boxes.append(_normalize_box(item))
            continue
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox", item.get("pred_bbox", item.get("box")))
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            boxes.append(_normalize_box(bbox))
    return boxes


def _find_inventory_record(inventory: dict[str, Any], score: str, page: str) -> dict[str, Any]:
    records = inventory.get("records", [])
    matches = [
        record
        for record in records
        if isinstance(record, dict)
        and str(record.get("score")) == score
        and str(record.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one inventory record for {score}/{page}, got {len(matches)}"
        )
    return matches[0]


def _recursive_page_file(root: Path, score: str, page: str, filename: str) -> Path | None:
    matches = []
    for path in root.rglob(filename):
        if "dense_candidate_reconstruction" in path.parts:
            continue
        text = str(path)
        if score in text and page in text:
            matches.append(path)
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        raise RuntimeError(
            f"Ambiguous {filename} for {score}/{page} below {root}: "
            + ", ".join(str(path) for path in unique)
        )
    return None


def _resolve_page_file(root: Path, score: str, page: str, filename: str) -> Path:
    record = PageRecord(score=score, page=page)
    path = find_page_file(root, record, filename)
    if path is None:
        path = _recursive_page_file(root, score, page, filename)
    if path is None or not path.exists():
        raise FileNotFoundError(f"Missing {filename} for {score}/{page} below {root}")
    return path


def _candidate_path(root: Path, score: str, page: str) -> Path:
    direct_paths = (
        root / score / page / CANDIDATE_FILENAME,
        root / f"eval2_{score}_{page}" / CANDIDATE_FILENAME,
        root / score / f"eval2_{score}_{page}" / CANDIDATE_FILENAME,
    )
    direct_matches = [path for path in direct_paths if path.is_file()]
    if len(direct_matches) == 1:
        return direct_matches[0]
    if len(direct_matches) > 1:
        raise RuntimeError(
            f"Ambiguous direct {CANDIDATE_FILENAME} for {score}/{page} below {root}: "
            + ", ".join(str(path) for path in direct_matches)
        )

    recursive_matches = sorted(
        {
            path
            for path in root.rglob(CANDIDATE_FILENAME)
            if path.is_file() and score in str(path) and page in str(path)
        }
    )
    if len(recursive_matches) == 1:
        return recursive_matches[0]
    if len(recursive_matches) > 1:
        raise RuntimeError(
            f"Ambiguous {CANDIDATE_FILENAME} for {score}/{page} below {root}: "
            + ", ".join(str(path) for path in recursive_matches)
        )
    raise FileNotFoundError(
        f"Missing {CANDIDATE_FILENAME} for {score}/{page} below {root}. "
        "Tried direct paths: " + ", ".join(str(path) for path in direct_paths)
    )


def _candidate_metrics(candidate: Box, target: Box) -> dict[str, Any]:
    return {
        "bbox": list(candidate),
        "xdist": center_distance_x(candidate, target),
        "vertical_overlap": barline_vertical_overlap(candidate, target),
        "matches": is_barline_match(
            candidate,
            target,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        ),
        "bbox_delta": [candidate[index] - target[index] for index in range(4)],
    }


def _stage_summary(boxes: Iterable[Box], target: Box, nearby_limit: int) -> dict[str, Any]:
    box_list = list(boxes)
    metrics = [_candidate_metrics(candidate, target) for candidate in box_list]
    matching = [item for item in metrics if item["matches"]]
    nearby = sorted(
        metrics,
        key=lambda item: (
            float(item["xdist"]),
            -float(item["vertical_overlap"]),
            item["bbox"],
        ),
    )[:nearby_limit]
    return {
        "candidate_count": len(box_list),
        "matching_count": len(matching),
        "present": bool(matching),
        "matching_candidates": matching,
        "nearby_candidates": nearby,
    }


def _candidate_height(box: Box) -> int:
    return abs(box[3] - box[1])


def _bbox_l1_distance(box_a: Box, box_b: Box) -> int:
    return sum(abs(box_a[index] - box_b[index]) for index in range(4))


def _historical_reference(boxes: Iterable[Box], target: Box) -> dict[str, Any] | None:
    matching = [
        candidate
        for candidate in boxes
        if is_barline_match(
            candidate,
            target,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
    ]
    if not matching:
        return None

    def rank_key(candidate: Box) -> tuple[float, ...]:
        rank = get_barline_match_rank(candidate, target, rule_name="center_anchor")
        return tuple(-float(value) for value in rank) + tuple(float(value) for value in candidate)

    reference = min(matching, key=rank_key)
    return {
        "bbox": list(reference),
        "height": _candidate_height(reference),
        "match_rank": list(get_barline_match_rank(reference, target, rule_name="center_anchor")),
        "matching_candidate_count": len(matching),
        "selection_reason": (
            "Selected the highest existing center_anchor match rank "
            "(vertical overlap, x closeness, IoU); bbox lexicographic order breaks ties."
        ),
    }


def _geometry_comparison(boxes: Iterable[Box], reference: Box) -> dict[str, Any]:
    box_list = list(boxes)
    reference_height = _candidate_height(reference)
    exact_present = reference in box_list
    if not box_list:
        return {
            "exact_present": exact_present,
            "closest_bbox": None,
            "bbox_delta": None,
            "xdist": None,
            "vertical_overlap": None,
            "reference_height": reference_height,
            "closest_height": None,
            "height_ratio": None,
            "top_delta": None,
            "bottom_delta": None,
        }

    closest = min(
        box_list,
        key=lambda candidate: (
            center_distance_x(candidate, reference),
            -barline_vertical_overlap(candidate, reference),
            _bbox_l1_distance(candidate, reference),
            candidate,
        ),
    )
    closest_height = _candidate_height(closest)
    return {
        "exact_present": exact_present,
        "closest_bbox": list(closest),
        "bbox_delta": [closest[index] - reference[index] for index in range(4)],
        "xdist": center_distance_x(closest, reference),
        "vertical_overlap": barline_vertical_overlap(closest, reference),
        "reference_height": reference_height,
        "closest_height": closest_height,
        "height_ratio": closest_height / reference_height if reference_height else None,
        "top_delta": closest[1] - reference[1],
        "bottom_delta": closest[3] - reference[3],
    }


def _historical_geometry_trace(
    comparisons: dict[str, dict[str, Any]],
    stage_boxes: dict[str, list[Box]],
    reference: Box,
    target: Box,
) -> dict[str, Any]:
    exact_stages = [name for name in STAGE_ORDER if comparisons[name]["exact_present"]]
    states = [("historical_reference", True)] + [
        (name, bool(comparisons[name]["exact_present"])) for name in STAGE_ORDER
    ]
    first_loss = next(
        (
            {"from": states[index - 1][0], "to": name, "change": "lost"}
            for index, (name, present) in enumerate(states)
            if index > 0 and not present and states[index - 1][1]
        ),
        None,
    )
    shorter_matching_by_stage = {
        name: sorted(
            (
                candidate
                for candidate in stage_boxes[name]
                if _candidate_height(candidate) < _candidate_height(reference)
                and is_barline_match(
                    candidate,
                    target,
                    rule_name="center_anchor",
                    vov_threshold=0.5,
                    xdist_threshold=12.0,
                )
            ),
            key=lambda candidate: (
                center_distance_x(candidate, reference),
                -barline_vertical_overlap(candidate, reference),
                _bbox_l1_distance(candidate, reference),
                candidate,
            ),
        )
        for name in STAGE_ORDER
    }
    first_shorter_matching_stage = next(
        (name for name in STAGE_ORDER if shorter_matching_by_stage[name]),
        None,
    )
    first_shorter_matching_bbox = (
        list(shorter_matching_by_stage[first_shorter_matching_stage][0])
        if first_shorter_matching_stage is not None
        else None
    )
    return {
        "last_exact_stage": exact_stages[-1] if exact_stages else None,
        "first_exact_loss_transition": first_loss,
        "first_shorter_matching_stage": first_shorter_matching_stage,
        "first_shorter_matching_bbox": first_shorter_matching_bbox,
        "closest_geometry_by_stage": comparisons,
    }


def _trace_transitions(stage_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    transitions = []
    previous_name = None
    previous_present = None
    for name in STAGE_ORDER:
        present = bool(stage_summaries[name]["present"])
        if previous_name is not None and present != previous_present:
            transitions.append(
                {
                    "from": previous_name,
                    "to": name,
                    "change": "appeared" if present else "lost",
                }
            )
        previous_name = name
        previous_present = present

    present_stages = [name for name in STAGE_ORDER if stage_summaries[name]["present"]]
    first_lost_transition = next(
        (transition for transition in transitions if transition["change"] == "lost"), None
    )
    return {
        "present_stages": present_stages,
        "last_present_stage": present_stages[-1] if present_stages else None,
        "first_lost_transition": first_lost_transition,
        "transitions": transitions,
    }


def _find_filter_items(
    suggestion: dict[str, Any], target: Box, disposition: str
) -> list[dict[str, Any]]:
    results = []
    for item in suggestion.get(disposition, []):
        if not isinstance(item, dict) or "bbox" not in item:
            continue
        bbox = _normalize_box(item["bbox"])
        metrics = _candidate_metrics(bbox, target)
        if metrics["matches"]:
            results.append({"disposition": disposition, **item, "match_metrics": metrics})
    return results


def _staff_mask_overlap(mask_path: Path | None, box: Box) -> float | None:
    if mask_path is None or not mask_path.exists():
        return None
    try:
        import cv2
    except ImportError:
        return None

    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    height, width = mask.shape[:2]
    x1, y1, x2, y2 = box
    x_lo = max(0, min(x1, x2))
    x_hi = min(width, max(x1, x2))
    y_lo = max(0, min(y1, y2))
    y_hi = min(height, max(y1, y2))
    if x_hi <= x_lo or y_hi <= y_lo:
        return 0.0
    crop = mask[y_lo:y_hi, x_lo:x_hi]
    return float((crop > 0).sum()) / float(crop.size)


def _parse_bbox(raw: str) -> Box:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must contain four comma-separated numbers")
    try:
        return _normalize_box(parts)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_report(
    *,
    inventory_path: Path,
    stage_e_root: Path,
    historical_root: Path,
    score: str,
    page: str,
    targets: list[Box],
    nearby_limit: int = 8,
) -> dict[str, Any]:
    inventory = _load_json(inventory_path)
    if not isinstance(inventory, dict):
        raise ValueError("Inventory JSON must be an object")
    record = _find_inventory_record(inventory, score, page)

    dense_root = stage_e_root / "dense_candidate_reconstruction"
    stage_paths = {
        "mixed_hybrid_input": Path(record["hybrid_predictions"]),
        "raw_dense_candidates": _candidate_path(
            dense_root / "probe_candidates_from_inventory", score, page
        ),
        "filtered_dense_candidates": _candidate_path(
            dense_root / "probe_candidates_filtered", score, page
        ),
        "probe_rescue_candidates": _candidate_path(
            dense_root / "probe_rescue_candidates", score, page
        ),
        "final_candidates": _resolve_page_file(stage_e_root, score, page, CANDIDATE_FILENAME),
        "historical_candidates": _resolve_page_file(
            historical_root, score, page, CANDIDATE_FILENAME
        ),
    }
    missing = [name for name, path in stage_paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing stage inputs: " + ", ".join(missing))

    stage_boxes = {name: _extract_boxes(_load_json(path)) for name, path in stage_paths.items()}
    suggestion_path = dense_root / "filter_suggestions" / score / f"{page}_suggestion.json"
    suggestion = _load_json(suggestion_path) if suggestion_path.exists() else None

    staff_mask_raw = record.get("staff_mask")
    staff_mask_path = Path(staff_mask_raw) if staff_mask_raw else None

    target_reports = []
    for target in targets:
        summaries = {
            name: _stage_summary(stage_boxes[name], target, nearby_limit) for name in stage_paths
        }
        filter_items: list[dict[str, Any]] = []
        if isinstance(suggestion, dict):
            filter_items.extend(_find_filter_items(suggestion, target, "keep"))
            filter_items.extend(_find_filter_items(suggestion, target, "drop_suggested"))

        historical_matches = summaries["historical_candidates"]["matching_candidates"]
        historical_reference = _historical_reference(stage_boxes["historical_candidates"], target)
        if historical_reference is None:
            geometry_trace = None
        else:
            reference_box = _normalize_box(historical_reference["bbox"])
            comparisons = {
                name: _geometry_comparison(stage_boxes[name], reference_box) for name in STAGE_ORDER
            }
            historical_reference["stage_comparisons"] = comparisons
            geometry_trace = _historical_geometry_trace(
                comparisons, stage_boxes, reference_box, target
            )
        historical_mask_assessments = [
            {
                "bbox": item["bbox"],
                "staff_mask_overlap": _staff_mask_overlap(
                    staff_mask_path, _normalize_box(item["bbox"])
                ),
            }
            for item in historical_matches
        ]
        target_reports.append(
            {
                "gt_bbox": list(target),
                "stages": summaries,
                "trace": _trace_transitions(summaries),
                "historical_reference": historical_reference,
                "historical_geometry_trace": geometry_trace,
                "filter_decisions": filter_items,
                "staff_mask": {
                    "path": str(staff_mask_path) if staff_mask_path else None,
                    "gt_overlap": _staff_mask_overlap(staff_mask_path, target),
                    "historical_candidate_overlaps": historical_mask_assessments,
                },
            }
        )

    return {
        "schema_version": "issue245.detector_fn_stage_trace.v2",
        "scope": {"score": score, "page": page},
        "inputs": {
            "inventory": str(inventory_path),
            "stage_e_root": str(stage_e_root),
            "historical_root": str(historical_root),
            "stage_paths": {name: str(path) for name, path in stage_paths.items()},
            "filter_suggestion": str(suggestion_path) if suggestion_path.exists() else None,
            "image": record.get("image"),
            "staff_mask": str(staff_mask_path) if staff_mask_path else None,
        },
        "matching_contract": {
            "rule_name": "center_anchor",
            "vov_threshold": 0.5,
            "xdist_threshold": 12.0,
        },
        "targets": target_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("logs/issue245_accuracy_first_mixed_route/mixed_inventory.json"),
    )
    parser.add_argument(
        "--stage-e-root",
        type=Path,
        default=Path("logs/issue245_accuracy_first_stage_e/stage_e_full_pipeline"),
    )
    parser.add_argument(
        "--historical-root",
        type=Path,
        default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"),
    )
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--gt-bbox", type=_parse_bbox, action="append", required=True)
    parser.add_argument("--nearby-limit", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        inventory_path=args.inventory,
        stage_e_root=args.stage_e_root,
        historical_root=args.historical_root,
        score=args.score,
        page=args.page,
        targets=args.gt_bbox,
        nearby_limit=args.nearby_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    for target in report["targets"]:
        trace = target["trace"]
        print(
            f"GT={target['gt_bbox']} last_present={trace['last_present_stage']} "
            f"first_lost={trace['first_lost_transition']}"
        )
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
