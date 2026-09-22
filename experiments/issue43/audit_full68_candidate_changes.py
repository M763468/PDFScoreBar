#!/usr/bin/env python3
"""Audit Issue #43 full68 candidate deltas without rerunning the detector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EDGE_RATIO = 0.12


def _host_path(value: str | Path) -> Path:
    path = Path(value)
    workspace = Path("/workspace")
    try:
        relative = path.relative_to(workspace)
    except ValueError:
        return path
    return ROOT / relative


def _load_json(path: str | Path) -> Any:
    return json.loads(_host_path(path).read_text(encoding="utf-8"))


def _normalize_box(item: Any) -> tuple[int, int, int, int] | None:
    if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 4:
        return tuple(int(round(float(value))) for value in item)
    if isinstance(item, Mapping):
        for key in ("barline_location", "orig_bbox", "pred_bbox", "bbox", "box"):
            value = item.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 4:
                return tuple(int(round(float(v))) for v in value)
    return None


def _boxes_from_payload(payload: Any) -> list[tuple[int, int, int, int]]:
    if isinstance(payload, Mapping):
        payload = payload.get("predictions", payload.get("boxes", payload))
    if not isinstance(payload, list):
        return []
    boxes = []
    for item in payload:
        box = _normalize_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def _parse_eval_run_dir(relative_path: str) -> tuple[str, str]:
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    run_dir = Path(relative_path).parts[0]
    if not run_dir.startswith("eval2_"):
        raise ValueError(f"Unexpected rescue run directory: {run_dir}")
    body = run_dir[len("eval2_") :]
    for score in sorted(full68_eval.SCORES, key=len, reverse=True):
        prefix = f"{score}_"
        if body.startswith(prefix):
            page = body[len(prefix) :]
            if page in full68_eval.SCORES[score]:
                return score, page
    raise ValueError(f"Unable to parse score/page from {run_dir}")


def _scored_map(root: Path, relative_candidate_path: str) -> dict[tuple[int, int, int, int], float]:
    scored_path = root / Path(relative_candidate_path).parent / "pipeline2_no_peak_scored.json"
    payload = _load_json(scored_path)
    result: dict[tuple[int, int, int, int], float] = {}
    if not isinstance(payload, list):
        return result
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        box = _normalize_box(item.get("bbox"))
        if box is None:
            continue
        score = float(item.get("score", 0.0))
        result[box] = max(score, result.get(box, float("-inf")))
    return result


def _load_inventory_records(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    provenance = report["provenance"]
    groups = provenance.get("upstream_groups", [])
    records: dict[tuple[str, str], Mapping[str, Any]] = {}
    for group in groups:
        inventory = _load_json(group["inventory"])
        for record in inventory.get("records", []):
            key = (str(record["score"]), str(record["page"]))
            records[key] = record
    return records


def _load_gt(score: str, page: str) -> list[tuple[int, int, int, int]]:
    path = ROOT / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
    return _boxes_from_payload(_load_json(path))


def _load_staff_units():
    from src.common.barline_units import load_page_staff_units

    return load_page_staff_units(ROOT / "data/evaluation2/staff_units.json")


def _load_existing_boxes(record: Mapping[str, Any]) -> list[tuple[int, int, int, int]]:
    return _boxes_from_payload(_load_json(record["hybrid_predictions"]))


def _pad_px_from_existing(existing_boxes: Sequence[tuple[int, int, int, int]]) -> int:
    heights = [abs(box[3] - box[1]) for box in existing_boxes if abs(box[3] - box[1]) > 0]
    if not heights:
        return 0
    return max(0, int(round(float(median(heights)) / 4.0)))


def _outside_staff_span_for_candidate_y(
    box: tuple[int, int, int, int],
    *,
    staff_mask_path: str | Path,
    image_width: int,
    pad_px: int,
) -> bool | None:
    mask = np.asarray(Image.open(_host_path(staff_mask_path)).convert("L"))
    if mask.ndim != 2 or mask.size == 0:
        return None

    y1 = max(0, min(mask.shape[0] - 1, min(box[1], box[3])))
    y2 = max(0, min(mask.shape[0] - 1, max(box[1], box[3])))
    if y2 < y1:
        return None
    xs = np.where(mask[y1 : y2 + 1, :].sum(axis=0) > 0)[0]
    if xs.size == 0:
        return None

    x1 = max(0, int(xs.min()) - pad_px)
    x2 = min(image_width - 1, int(xs.max()) + pad_px)
    cx = (box[0] + box[2]) / 2.0
    return cx < x1 or cx > x2


def _matches_any_gt(
    box: tuple[int, int, int, int],
    *,
    gt_boxes: Sequence[tuple[int, int, int, int]],
    unit_size: float,
) -> bool:
    from src.common.barline_evaluation import CENTER_ANCHOR_XDIST_UNIT_RATIO, is_barline_match

    return any(
        is_barline_match(
            box,
            gt,
            rule_name="center_anchor",
            vov_threshold=0.5,
            unit_size=unit_size,
            xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
        )
        for gt in gt_boxes
    )


def _audit_box(
    box: tuple[int, int, int, int],
    *,
    score_value: float | None,
    threshold: float,
    score: str,
    page: str,
    record: Mapping[str, Any],
    page_unit: Any,
    gt_boxes: Sequence[tuple[int, int, int, int]],
    pad_px: int,
) -> dict[str, Any]:
    width = int(page_unit.coordinate_width)
    cx = (box[0] + box[2]) / 2.0
    x_ratio = cx / float(width)
    return {
        "bbox": list(box),
        "cnn_score": score_value,
        "cnn_at_or_above_threshold": (
            score_value is not None and score_value >= threshold
        ),
        "x_center_ratio": x_ratio,
        "left_edge_12pct": x_ratio < EDGE_RATIO,
        "right_edge_12pct": x_ratio > 1.0 - EDGE_RATIO,
        "outer_edge_12pct": x_ratio < EDGE_RATIO or x_ratio > 1.0 - EDGE_RATIO,
        "outside_staff_span_for_candidate_y": _outside_staff_span_for_candidate_y(
            box,
            staff_mask_path=record["staff_mask"],
            image_width=width,
            pad_px=pad_px,
        ),
        "matches_any_gt": _matches_any_gt(
            box,
            gt_boxes=gt_boxes,
            unit_size=float(page_unit.unit_size),
        ),
        "score": score,
        "page": page,
    }


def _summarize(records: Sequence[Mapping[str, Any]], *, threshold: float) -> dict[str, Any]:
    scores = [
        float(record["cnn_score"])
        for record in records
        if record.get("cnn_score") is not None
    ]
    outside_known = [
        bool(record["outside_staff_span_for_candidate_y"])
        for record in records
        if record.get("outside_staff_span_for_candidate_y") is not None
    ]
    return {
        "count": len(records),
        "cnn_score_available": len(scores),
        "cnn_at_or_above_threshold": sum(
            bool(record["cnn_at_or_above_threshold"]) for record in records
        ),
        "cnn_below_threshold": sum(
            record.get("cnn_score") is not None
            and float(record["cnn_score"]) < threshold
            for record in records
        ),
        "cnn_score_max": max(scores) if scores else None,
        "cnn_score_median": median(scores) if scores else None,
        "outer_edge_12pct": sum(bool(record["outer_edge_12pct"]) for record in records),
        "outside_staff_span_known": len(outside_known),
        "outside_staff_span": sum(outside_known),
        "matches_any_gt": sum(bool(record["matches_any_gt"]) for record in records),
    }


def audit(report_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    threshold = float(report["provenance"]["cnn_threshold"])
    full_root = _host_path(report["variants"]["full_width"]["probe_rescue_root"])
    staff_root = _host_path(report["variants"]["staff_mask"]["probe_rescue_root"])
    changes = report["comparison"]["stages"]["probe_rescue_candidates"]["changes"]
    inventory_records = _load_inventory_records(report)
    staff_units = _load_staff_units()

    removed_records: list[dict[str, Any]] = []
    added_records: list[dict[str, Any]] = []

    for change in changes:
        relative = str(change["path"])
        score, page = _parse_eval_run_dir(relative)
        key = (score, page)
        record = inventory_records[key]
        page_unit = staff_units[f"{score}/{page}"]
        gt_boxes = _load_gt(score, page)
        pad_px = _pad_px_from_existing(_load_existing_boxes(record))

        full_scores = _scored_map(full_root, relative)
        staff_scores = _scored_map(staff_root, relative)

        for raw_box in change.get("removed_boxes", []):
            box = _normalize_box(raw_box)
            if box is None:
                continue
            removed_records.append(
                _audit_box(
                    box,
                    score_value=full_scores.get(box),
                    threshold=threshold,
                    score=score,
                    page=page,
                    record=record,
                    page_unit=page_unit,
                    gt_boxes=gt_boxes,
                    pad_px=pad_px,
                )
            )

        for raw_box in change.get("added_boxes", []):
            box = _normalize_box(raw_box)
            if box is None:
                continue
            added_records.append(
                _audit_box(
                    box,
                    score_value=staff_scores.get(box),
                    threshold=threshold,
                    score=score,
                    page=page,
                    record=record,
                    page_unit=page_unit,
                    gt_boxes=gt_boxes,
                    pad_px=pad_px,
                )
            )

    return {
        "schema_version": "issue43.probe_x_domain_candidate_audit.v1",
        "report": str(report_path),
        "cnn_threshold": threshold,
        "removed": {
            "summary": _summarize(removed_records, threshold=threshold),
            "records": removed_records,
        },
        "added": {
            "summary": _summarize(added_records, threshold=threshold),
            "records": added_records,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = audit(args.report.resolve())
    output = args.output
    if output is None:
        output = args.report.resolve().parent / "candidate_delta_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== REMOVED RESCUE CANDIDATES ===")
    for key, value in result["removed"]["summary"].items():
        print(f"{key}={value}")
    print()
    print("=== ADDED RESCUE CANDIDATES ===")
    for key, value in result["added"]["summary"].items():
        print(f"{key}={value}")
    print()
    print(f"audit={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
