#!/usr/bin/env python3
"""Classify evaluation2 detection residuals by likely measure-count impact."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
)
from tools.eval2_full_detection_report import (  # noqa: E402
    Box,
    boxes_from_records,
    find_gt_file,
    find_page_dir,
    load_gt_boxes,
    load_json,
    score_for_box,
)


def estimate_unit_size(scored_records: list[Any]) -> float:
    heights = [
        abs(float(item["bbox"][3]) - float(item["bbox"][1]))
        for item in scored_records
        if isinstance(item, dict) and item.get("bbox") and float(item.get("score", 0.0)) >= 0.5
    ]
    if not heights:
        heights = [
            abs(float(item["bbox"][3]) - float(item["bbox"][1]))
            for item in scored_records
            if isinstance(item, dict) and item.get("bbox")
        ]
    if not heights:
        return 25.0
    heights.sort()
    mid = len(heights) // 2
    median = heights[mid] if len(heights) % 2 else (heights[mid - 1] + heights[mid]) / 2.0
    return max(1.0, median / 4.0)


def matching_gt_indices(match_result: Any) -> set[int]:
    return {match.gt_index for match in match_result.matches}


def matching_pred_indices(match_result: Any) -> set[int]:
    return {match.pred_index for match in match_result.matches}


def nearby_matched_prediction(
    gt_box: Box,
    pred_boxes: list[Box],
    matched_preds: set[int],
    *,
    x_threshold: float,
    vov_threshold: float,
) -> tuple[int | None, Box | None, float | None, float | None]:
    best: tuple[int | None, Box | None, float | None, float | None] = (None, None, None, None)
    for pred_idx in matched_preds:
        pred = pred_boxes[pred_idx]
        vov = barline_vertical_overlap(gt_box, pred)
        if vov < vov_threshold:
            continue
        xdist = center_distance_x(gt_box, pred)
        if xdist > x_threshold:
            continue
        if best[2] is None or xdist < best[2]:
            best = (pred_idx, pred, xdist, vov)
    return best


def nearby_gt(
    box: Box,
    gt_boxes: list[Box],
    *,
    exclude_index: int | None = None,
    x_threshold: float,
    vov_threshold: float,
) -> tuple[int | None, Box | None, float | None, float | None]:
    best: tuple[int | None, Box | None, float | None, float | None] = (None, None, None, None)
    for gt_idx, gt_box in enumerate(gt_boxes):
        if gt_idx == exclude_index:
            continue
        vov = barline_vertical_overlap(box, gt_box)
        if vov < vov_threshold:
            continue
        xdist = center_distance_x(box, gt_box)
        if xdist > x_threshold:
            continue
        if best[2] is None or xdist < best[2]:
            best = (gt_idx, gt_box, xdist, vov)
    return best


def best_near_score(
    gt_box: Box,
    scored_records: list[Any],
    *,
    x_threshold: float,
    vov_threshold: float,
) -> float | None:
    best: float | None = None
    for item in scored_records:
        if not isinstance(item, dict) or not item.get("bbox"):
            continue
        pred = tuple(int(v) for v in item["bbox"][:4])
        if barline_vertical_overlap(gt_box, pred) < vov_threshold:
            continue
        if center_distance_x(gt_box, pred) > x_threshold:
            continue
        score = float(item.get("score", 0.0))
        best = score if best is None else max(best, score)
    return best


def classify_fn(
    *,
    gt_box: Box,
    gt_record: dict[str, Any],
    gt_index: int,
    pred_boxes: list[Box],
    matched_preds: set[int],
    gt_boxes: list[Box],
    gt_records: list[Any],
    scored_records: list[Any],
    candidate_fn_indices: set[int],
    logic_x_threshold: float,
    vov_threshold: float,
) -> dict[str, Any]:
    near_pred_idx, near_pred_box, near_pred_xdist, near_pred_vov = nearby_matched_prediction(
        gt_box,
        pred_boxes,
        matched_preds,
        x_threshold=logic_x_threshold,
        vov_threshold=vov_threshold,
    )
    near_gt_idx, near_gt_box, near_gt_xdist, near_gt_vov = nearby_gt(
        gt_box,
        gt_boxes,
        exclude_index=gt_index,
        x_threshold=logic_x_threshold,
        vov_threshold=vov_threshold,
    )
    near_gt_record = gt_records[near_gt_idx] if near_gt_idx is not None else {}
    gt_type = gt_record.get("barline_type", "")
    near_gt_type = (
        near_gt_record.get("barline_type", "") if isinstance(near_gt_record, dict) else ""
    )
    best_score = best_near_score(
        gt_box,
        scored_records,
        x_threshold=12.0,
        vov_threshold=vov_threshold,
    )

    if near_pred_idx is not None:
        category = "covered_by_matched_prediction"
        count_impact = "likely_count_neutral"
    elif gt_type in {"double_barline", "end_barline", "repeat"} or near_gt_type in {
        "double_barline",
        "end_barline",
        "repeat",
    }:
        category = "complex_pair_uncovered"
        count_impact = "likely_count_affecting"
    else:
        category = "isolated_missing"
        count_impact = "likely_count_affecting"

    fn_stage = "FN_det" if gt_index in candidate_fn_indices else "FN_cnn_or_post"
    if best_score is not None and best_score < 0.08:
        fn_stage = "FN_low_score"

    return {
        "residual_type": "FN",
        "category": category,
        "count_impact": count_impact,
        "fn_stage": fn_stage,
        "gt_type": gt_type,
        "gt_measure": gt_record.get("measure_number"),
        "nearest_gt_index": near_gt_idx,
        "nearest_gt_type": near_gt_type,
        "nearest_gt_xdist": near_gt_xdist,
        "nearest_gt_vov": near_gt_vov,
        "nearest_pred_index": near_pred_idx,
        "nearest_pred_bbox": near_pred_box,
        "nearest_pred_xdist": near_pred_xdist,
        "nearest_pred_vov": near_pred_vov,
        "best_near_score": best_score,
    }


def classify_fp(
    *,
    pred_box: Box,
    pred_index: int,
    gt_boxes: list[Box],
    gt_records: list[Any],
    matched_gt: set[int],
    scored_records: list[Any],
    unit_size: float,
    logic_x_threshold: float,
    vov_threshold: float,
) -> dict[str, Any]:
    near_gt_idx, near_gt_box, near_gt_xdist, near_gt_vov = nearby_gt(
        pred_box,
        gt_boxes,
        x_threshold=logic_x_threshold,
        vov_threshold=vov_threshold,
    )
    near_gt_record = gt_records[near_gt_idx] if near_gt_idx is not None else {}
    pred_h = max(1.0, float(pred_box[3] - pred_box[1]))
    height_unit_ratio = pred_h / unit_size
    score = score_for_box(scored_records, pred_box)

    if near_gt_idx is not None and near_gt_idx in matched_gt:
        category = "near_matched_gt_duplicate"
        count_impact = "dedup_dependent"
    elif height_unit_ratio >= 7.5:
        category = "tall_or_system_spanning_fp"
        count_impact = "likely_count_affecting"
    elif near_gt_idx is not None:
        category = "near_unmatched_gt_soft_fp"
        count_impact = "uncertain"
    else:
        category = "remote_fp"
        count_impact = "likely_count_affecting"

    return {
        "residual_type": "FP",
        "category": category,
        "count_impact": count_impact,
        "fn_stage": "",
        "gt_type": "",
        "gt_measure": "",
        "nearest_gt_index": near_gt_idx,
        "nearest_gt_type": near_gt_record.get("barline_type", "")
        if isinstance(near_gt_record, dict)
        else "",
        "nearest_gt_xdist": near_gt_xdist,
        "nearest_gt_vov": near_gt_vov,
        "nearest_pred_index": pred_index,
        "nearest_pred_bbox": pred_box,
        "nearest_pred_xdist": "",
        "nearest_pred_vov": "",
        "best_near_score": score,
        "height_unit_ratio": height_unit_ratio,
        "numbering_dedup_likely": bool(near_gt_xdist is not None and near_gt_xdist < 15.0),
    }


def visual_path(
    *,
    report_dir: Path,
    residual_type: str,
    score: str,
    page: str,
    index: int,
) -> str:
    if residual_type == "FN":
        path = report_dir / "visuals" / "fn_crops" / score / f"{page}_FN_gt{index}.png"
        return str(path)
    pattern = report_dir / "visuals" / "fp_crops" / score / f"{page}_FP_pred{index}_*.png"
    matches = sorted(glob.glob(str(pattern)))
    return matches[0] if matches else ""


def overlay_path(*, report_dir: Path, score: str, page: str) -> str:
    path = report_dir / "visuals" / "overlays" / score / f"{page}_tp_fp_fn_overlay.png"
    return str(path) if path.exists() else ""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_review_markdown(
    path: Path, rows: list[dict[str, Any]], summary_rows: list[dict[str, Any]]
) -> None:
    lines = [
        "# Evaluation2 Residual Measure Impact Review",
        "",
        "This file indexes residual crop/overlay images generated by "
        "`tools/eval2_full_detection_report.py` and groups them by likely measure-count impact.",
        "",
        "## Summary",
        "",
        "| residual_type | category | count_impact | count |",
        "| --- | --- | --- | ---: |",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['residual_type']} | {row['category']} | {row['count_impact']} | {row['count']} |"
        )

    lines.extend(["", "## Review Index", ""])
    for row in rows:
        visual = row.get("visual_path", "")
        overlay = row.get("overlay_path", "")
        label = (
            f"{row['residual_type']} {row['score']} {row['page']} idx={row['index']} "
            f"{row['category']} {row['count_impact']}"
        )
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- bbox: `{row['bbox']}`")
        lines.append(f"- stage/type: `{row.get('fn_stage', '')}` / `{row.get('gt_type', '')}`")
        lines.append(
            "- nearest: "
            f"gt_idx=`{row.get('nearest_gt_index', '')}`, "
            f"gt_xdist=`{row.get('nearest_gt_xdist', '')}`, "
            f"pred_idx=`{row.get('nearest_pred_index', '')}`, "
            f"pred_xdist=`{row.get('nearest_pred_xdist', '')}`"
        )
        if visual:
            lines.append(f"- crop: [{Path(visual).name}]({visual})")
        if overlay:
            lines.append(f"- overlay: [{Path(overlay).name}]({overlay})")
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--logic-x-threshold", type=float, default=20.0)
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    manifest = load_json(args.manifest)
    for item in manifest:
        score = item["score"]
        run_id = item["run_id"]
        run_dir = args.run_root / run_id
        if not run_dir.exists():
            continue
        for page in item["pages"]:
            page_dir = find_page_dir(run_dir, run_id, page)
            gt_file = find_gt_file(args.gt_root, score, page)
            if not page_dir or not gt_file:
                continue
            filtered_path = page_dir / "pipeline2_no_peak_filtered_cnn.json"
            scored_path = page_dir / "pipeline2_no_peak_scored.json"
            candidates_path = page_dir / "pipeline2_no_peak_candidates.json"
            if (
                not filtered_path.exists()
                or not scored_path.exists()
                or not candidates_path.exists()
            ):
                continue

            gt_records = load_json(gt_file)
            gt_boxes = load_gt_boxes(gt_file)
            pred_boxes = boxes_from_records(load_json(filtered_path))
            scored_records = load_json(scored_path)
            candidate_boxes = boxes_from_records(load_json(candidates_path))
            unit_size = estimate_unit_size(scored_records)

            match_result = greedy_barline_match(
                pred_boxes,
                gt_boxes,
                rule_name="center_anchor",
                vov_threshold=args.vov_threshold,
                xdist_threshold=12.0,
            )
            candidate_match = greedy_barline_match(
                candidate_boxes,
                gt_boxes,
                rule_name="center_anchor",
                vov_threshold=args.vov_threshold,
                xdist_threshold=12.0,
            )
            matched_gt = matching_gt_indices(match_result)
            matched_preds = matching_pred_indices(match_result)
            candidate_fn_indices = set(candidate_match.false_negative_indices)

            for gt_index in match_result.false_negative_indices:
                gt_record = gt_records[gt_index] if isinstance(gt_records[gt_index], dict) else {}
                classified = classify_fn(
                    gt_box=gt_boxes[gt_index],
                    gt_record=gt_record,
                    gt_index=gt_index,
                    pred_boxes=pred_boxes,
                    matched_preds=matched_preds,
                    gt_boxes=gt_boxes,
                    gt_records=gt_records,
                    scored_records=scored_records,
                    candidate_fn_indices=candidate_fn_indices,
                    logic_x_threshold=args.logic_x_threshold,
                    vov_threshold=args.vov_threshold,
                )
                rows.append(
                    {
                        "score": score,
                        "page": page,
                        "index": gt_index,
                        "bbox": json.dumps(gt_boxes[gt_index]),
                        **classified,
                        "height_unit_ratio": "",
                        "numbering_dedup_likely": "",
                        "visual_path": visual_path(
                            report_dir=args.report_dir,
                            residual_type="FN",
                            score=score,
                            page=page,
                            index=gt_index,
                        ),
                        "overlay_path": overlay_path(
                            report_dir=args.report_dir, score=score, page=page
                        ),
                    }
                )

            for pred_index in match_result.false_positive_indices:
                classified = classify_fp(
                    pred_box=pred_boxes[pred_index],
                    pred_index=pred_index,
                    gt_boxes=gt_boxes,
                    gt_records=gt_records,
                    matched_gt=matched_gt,
                    scored_records=scored_records,
                    unit_size=unit_size,
                    logic_x_threshold=args.logic_x_threshold,
                    vov_threshold=args.vov_threshold,
                )
                rows.append(
                    {
                        "score": score,
                        "page": page,
                        "index": pred_index,
                        "bbox": json.dumps(pred_boxes[pred_index]),
                        **classified,
                        "visual_path": visual_path(
                            report_dir=args.report_dir,
                            residual_type="FP",
                            score=score,
                            page=page,
                            index=pred_index,
                        ),
                        "overlay_path": overlay_path(
                            report_dir=args.report_dir, score=score, page=page
                        ),
                    }
                )

    summary_counter = Counter(
        (row["residual_type"], row["category"], row["count_impact"]) for row in rows
    )
    summary_rows = [
        {
            "residual_type": residual_type,
            "category": category,
            "count_impact": count_impact,
            "count": count,
        }
        for (residual_type, category, count_impact), count in sorted(summary_counter.items())
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "measure_impact_residuals.csv", rows)
    write_csv(args.output_dir / "measure_impact_summary.csv", summary_rows)
    (args.output_dir / "measure_impact_summary.json").write_text(
        json.dumps(summary_rows, indent=2, ensure_ascii=False)
    )
    write_review_markdown(args.output_dir / "measure_impact_review.md", rows, summary_rows)
    print(f"Wrote {args.output_dir / 'measure_impact_residuals.csv'}")
    print(f"Wrote {args.output_dir / 'measure_impact_review.md'}")


if __name__ == "__main__":
    main()
