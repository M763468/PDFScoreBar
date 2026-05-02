#!/usr/bin/env python3
"""Evaluate measure-count KPI from evaluation2 detection outputs."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_vertical_overlap  # noqa: E402
from src.measure_numbering.pipeline import MeasureNumberingPipeline  # noqa: E402
from src.measure_numbering.types import Score  # noqa: E402
from tools.eval2_full_detection_report import (  # noqa: E402
    Box,
    boxes_from_records,
    find_gt_file,
    find_page_dir,
    load_gt_boxes,
    load_json,
)


def x_iou(a: Box, b: Box) -> float:
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    union = max(a[2], b[2]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def box_area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection_area(a: Box, b: Box) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def measure_iou_2d(a: Box, b: Box) -> float:
    inter = intersection_area(a, b)
    union = box_area(a) + box_area(b) - inter
    return inter / union if union > 0 else 0.0


def extract_measures(page: Any) -> list[dict[str, Any]]:
    measures = []
    for system_index, system in enumerate(page.systems):
        for measure in system.measures:
            bbox = (
                measure.bbox.x1,
                measure.bbox.y1,
                measure.bbox.x2,
                measure.bbox.y2,
            )
            measures.append(
                {
                    "number": int(measure.number),
                    "bbox": bbox,
                    "system_index": system_index,
                }
            )
    return measures


def measure_local_kpis(
    gt_measures: Sequence[dict[str, Any]],
    pred_measures: Sequence[dict[str, Any]],
    *,
    x_iou_threshold: float,
    min_vertical_overlap: float,
    nlc_iou_threshold: float,
) -> dict[str, float | int | None]:
    pairs: list[tuple[tuple[float, float], int, int]] = []
    for pred_index, pred_measure in enumerate(pred_measures):
        pred_box = pred_measure["bbox"]
        for gt_index, gt_measure in enumerate(gt_measures):
            gt_box = gt_measure["bbox"]
            xiou = x_iou(pred_box, gt_box)
            vov = barline_vertical_overlap(pred_box, gt_box)
            if xiou >= x_iou_threshold and vov >= min_vertical_overlap:
                pairs.append(((xiou, vov), pred_index, gt_index))
    pairs.sort(reverse=True)

    used_pred: set[int] = set()
    used_gt: set[int] = set()
    for _, pred_index, gt_index in pairs:
        if pred_index in used_pred or gt_index in used_gt:
            continue
        used_pred.add(pred_index)
        used_gt.add(gt_index)

    tp = len(used_pred)
    fp = len(pred_measures) - tp
    fn = len(gt_measures) - tp

    pred_by_number: dict[int, list[Box]] = defaultdict(list)
    gt_by_number: dict[int, list[Box]] = defaultdict(list)
    for pred_measure in pred_measures:
        pred_by_number[int(pred_measure["number"])].append(pred_measure["bbox"])
    for gt_measure in gt_measures:
        gt_by_number[int(gt_measure["number"])].append(gt_measure["bbox"])

    nlc_total = 0
    nlc_hits = 0
    for number, gt_boxes in gt_by_number.items():
        pred_boxes = pred_by_number.get(number, [])
        for gt_box in gt_boxes:
            nlc_total += 1
            best = max((measure_iou_2d(pred_box, gt_box) for pred_box in pred_boxes), default=0.0)
            if best >= nlc_iou_threshold:
                nlc_hits += 1

    return {
        "measure_match_tp": tp,
        "measure_match_fp": fp,
        "measure_match_fn": fn,
        "measure_match_recall": tp / len(gt_measures) if gt_measures else 0.0,
        "measure_match_precision": tp / len(pred_measures) if pred_measures else 0.0,
        "measure_nlc_rate": nlc_hits / nlc_total if nlc_total else None,
    }


def find_staff_mask(hybrid_output_dir: Path, page: str) -> Path | None:
    candidates = [
        hybrid_output_dir / "baseline" / "batch" / page / f"{page}_staff_mask.png",
        hybrid_output_dir / "sr" / "batch" / page / f"{page}_staff_mask.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    matches = sorted(hybrid_output_dir.glob(f"**/{page}_staff_mask.png"))
    return matches[0] if matches else None


def find_hybrid_output_dir(run_dir: Path, run_id: str, fallback_root: Path) -> Path | None:
    detection_manifest = run_dir / "detection_only_manifest.json"
    if detection_manifest.exists():
        payload = load_json(detection_manifest)
        manifest_dir = Path(payload["hybrid_output_dir"])
        if manifest_dir.exists():
            return manifest_dir

    fallback_dir = fallback_root / run_id
    if fallback_dir.exists():
        return fallback_dir
    return None


def run_numbering(
    pipeline: MeasureNumberingPipeline,
    boxes: list[Box],
    staff_mask: Path,
    image_path: Path,
    page_number: int,
) -> list[dict[str, Any]] | None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    page_obj = pipeline.process_page(
        [list(box) for box in boxes],
        staff_mask,
        (width, height),
        page_number=page_number,
        image=image,
    )
    score = Score()
    score.pages.append(page_obj)
    pipeline.numberer.number_score(score, start_number=1)
    return extract_measures(page_obj)


def estimate_unit_size_from_records(records: Sequence[Any], threshold: float) -> float:
    heights = [
        abs(float(item["bbox"][3]) - float(item["bbox"][1]))
        for item in records
        if isinstance(item, dict)
        and item.get("bbox")
        and len(item["bbox"]) == 4
        and float(item.get("score", 0.0)) >= threshold
    ]
    if not heights:
        heights = [
            abs(float(item["bbox"][3]) - float(item["bbox"][1]))
            for item in records
            if isinstance(item, dict) and item.get("bbox") and len(item["bbox"]) == 4
        ]
    if not heights:
        return 25.0
    heights.sort()
    mid = len(heights) // 2
    median = heights[mid] if len(heights) % 2 else (heights[mid - 1] + heights[mid]) / 2.0
    return max(1.0, median / 4.0)


def parse_ratio_token(text: str) -> float:
    return float(text.replace("p", "."))


def apply_center_nms(
    records: list[dict[str, Any]], x_dist_unit_ratio: float
) -> list[dict[str, Any]]:
    if x_dist_unit_ratio <= 0:
        return records
    sorted_records = sorted(records, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    kept: list[dict[str, Any]] = []
    for item in sorted_records:
        box = tuple(int(v) for v in item["bbox"][:4])
        unit_size = max(1.0, abs(float(box[3] - box[1])) / 4.0)
        cx = (box[0] + box[2]) / 2.0
        duplicate = False
        for kept_item in kept:
            kept_box = tuple(int(v) for v in kept_item["bbox"][:4])
            kept_cx = (kept_box[0] + kept_box[2]) / 2.0
            if (
                abs(cx - kept_cx) < unit_size * x_dist_unit_ratio
                and barline_vertical_overlap(box, kept_box) >= 0.5
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def parse_optional_ratio_token(text: str | None) -> float | None:
    return parse_ratio_token(text) if text else None


def variant_boxes(
    variant: str, filtered_records: list[Any], scored_records: list[Any]
) -> list[Box]:
    if variant == "filtered":
        return boxes_from_records(filtered_records)
    match = re.fullmatch(
        r"score_ge_(?P<threshold>\d+p?\d*)"
        r"(?:_minh_(?P<minh>\d+p?\d*))?"
        r"(?:_maxh_(?P<maxh>\d+p?\d*))?"
        r"(?:_softshort_(?P<softshort>\d+p?\d*)_scorelt_(?P<softscore>\d+p?\d*))?"
        r"(?:_xnms_(?P<xnms>\d+p?\d*))?",
        variant,
    )
    if match:
        threshold = parse_ratio_token(match.group("threshold"))
        min_height_ratio = parse_optional_ratio_token(match.group("minh"))
        max_height_ratio = parse_optional_ratio_token(match.group("maxh"))
        soft_short_height_ratio = parse_optional_ratio_token(match.group("softshort"))
        soft_short_max_score = parse_optional_ratio_token(match.group("softscore"))
        x_nms_ratio = parse_ratio_token(match.group("xnms")) if match.group("xnms") else 0.0
        unit_size = estimate_unit_size_from_records(scored_records, threshold)
        records: list[dict[str, Any]] = []
        for item in scored_records:
            if not isinstance(item, dict) or not item.get("bbox") or len(item["bbox"]) != 4:
                continue
            score = float(item.get("score", 0.0))
            if score < threshold:
                continue
            height_ratio = abs(float(item["bbox"][3]) - float(item["bbox"][1])) / unit_size
            if min_height_ratio is not None and height_ratio < min_height_ratio:
                continue
            if max_height_ratio is not None and height_ratio > max_height_ratio:
                continue
            if (
                soft_short_height_ratio is not None
                and soft_short_max_score is not None
                and score < soft_short_max_score
                and height_ratio < soft_short_height_ratio
            ):
                continue
            records.append(item)
        return boxes_from_records(apply_center_nms(records, x_nms_ratio))
    raise ValueError(f"Unknown variant: {variant}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_review_markdown(
    path: Path,
    summary_rows: list[dict[str, Any]],
    delta_rows: list[dict[str, Any]],
) -> None:
    report_root = path.parent.parent
    lines = [
        "# Measure Count KPI Review",
        "",
        "## Summary",
        "",
        "| variant | score | pages | pred | gt | delta | abs_delta | delta_pages | precision | recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {variant} | {score} | {pages} | {pred_measure_count} | "
            "{gt_measure_count} | {measure_delta} | {measure_abs_delta_sum} | "
            "{pages_with_count_delta} | {measure_match_precision:.6f} | "
            "{measure_match_recall:.6f} |".format(
                **{
                    **row,
                    "measure_match_precision": float(row["measure_match_precision"]),
                    "measure_match_recall": float(row["measure_match_recall"]),
                }
            )
        )

    lines.extend(
        [
            "",
            "## Visual Review Entrypoints",
            "",
            f"- FP crops: `{report_root / 'visuals' / 'fp_crops'}`",
            f"- FN crops: `{report_root / 'visuals' / 'fn_crops'}`",
            f"- TP/FP/FN overlays: `{report_root / 'visuals' / 'overlays'}`",
            "",
            "## Pages With Measure Count Delta",
            "",
            "| variant | score | page | pred | gt | delta | overlay |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in delta_rows:
        overlay = (
            report_root
            / "visuals"
            / "overlays"
            / str(row["score"])
            / f"{row['page']}_tp_fp_fn_overlay.png"
        )
        overlay_text = str(overlay) if overlay.exists() else ""
        lines.append(
            "| {variant} | {score} | {page} | {pred_measure_count} | "
            "{gt_measure_count} | {measure_delta} | `{overlay}` |".format(
                overlay=overlay_text,
                **row,
            )
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--hybrid-root",
        type=Path,
        default=Path("logs/hybrid_generalization/verification_full_v12_restore"),
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["filtered", "score_ge_0p5", "score_ge_0p5_minh_2p8"],
    )
    parser.add_argument("--measure-match-x-iou-threshold", type=float, default=0.85)
    parser.add_argument("--measure-match-min-vertical-overlap", type=float, default=0.5)
    parser.add_argument("--measure-nlc-iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    pipeline = MeasureNumberingPipeline()
    per_page_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    for item in manifest:
        score_name = item["score"]
        run_id = item["run_id"]
        run_dir = args.run_root / run_id
        if not run_dir.exists():
            missing_rows.append({"score": score_name, "page": "", "reason": "run_dir_missing"})
            continue

        hybrid_output_dir = find_hybrid_output_dir(run_dir, run_id, args.hybrid_root)
        if hybrid_output_dir is None:
            missing_rows.append(
                {"score": score_name, "page": "", "reason": "hybrid_output_missing"}
            )
            continue

        for page_number, page in enumerate(item["pages"], start=1):
            page_dir = find_page_dir(run_dir, run_id, page)
            gt_file = find_gt_file(args.gt_root, score_name, page)
            image_path = args.images_root / score_name / f"{page}.png"
            staff_mask = find_staff_mask(hybrid_output_dir, page)
            if not page_dir or not gt_file or not image_path.exists() or staff_mask is None:
                missing_rows.append(
                    {
                        "score": score_name,
                        "page": page,
                        "reason": "page_dir_or_gt_or_image_or_staff_mask_missing",
                    }
                )
                continue

            filtered_path = page_dir / "pipeline2_no_peak_filtered_cnn.json"
            scored_path = page_dir / "pipeline2_no_peak_scored.json"
            if not filtered_path.exists() or not scored_path.exists():
                missing_rows.append(
                    {"score": score_name, "page": page, "reason": "cnn_json_missing"}
                )
                continue

            gt_boxes = load_gt_boxes(gt_file)
            gt_measures = run_numbering(pipeline, gt_boxes, staff_mask, image_path, page_number)
            if gt_measures is None:
                missing_rows.append(
                    {"score": score_name, "page": page, "reason": "gt_numbering_failed"}
                )
                continue

            filtered_records = load_json(filtered_path)
            scored_records = load_json(scored_path)
            for variant in args.variants:
                pred_boxes = variant_boxes(variant, filtered_records, scored_records)
                pred_measures = run_numbering(
                    pipeline, pred_boxes, staff_mask, image_path, page_number
                )
                if pred_measures is None:
                    missing_rows.append(
                        {"score": score_name, "page": page, "reason": f"{variant}_numbering_failed"}
                    )
                    continue
                kpis = measure_local_kpis(
                    gt_measures,
                    pred_measures,
                    x_iou_threshold=args.measure_match_x_iou_threshold,
                    min_vertical_overlap=args.measure_match_min_vertical_overlap,
                    nlc_iou_threshold=args.measure_nlc_iou_threshold,
                )
                pred_count = len(pred_measures)
                gt_count = len(gt_measures)
                per_page_rows.append(
                    {
                        "variant": variant,
                        "score": score_name,
                        "page": page,
                        "pred_measure_count": pred_count,
                        "gt_measure_count": gt_count,
                        "measure_delta": pred_count - gt_count,
                        "measure_abs_delta": abs(pred_count - gt_count),
                        "pred_barline_count": len(pred_boxes),
                        "gt_barline_count": len(gt_boxes),
                        "staff_mask": str(staff_mask),
                        "image_path": str(image_path),
                        **kpis,
                    }
                )

    summary_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in per_page_rows:
        grouped[(row["variant"], row["score"])].append(row)
        grouped[(row["variant"], "GLOBAL_TOTAL")].append(row)

    for (variant, score_name), rows in sorted(grouped.items()):
        pred_total = sum(int(row["pred_measure_count"]) for row in rows)
        gt_total = sum(int(row["gt_measure_count"]) for row in rows)
        abs_total = sum(int(row["measure_abs_delta"]) for row in rows)
        pages_with_delta = sum(1 for row in rows if int(row["measure_abs_delta"]) > 0)
        match_tp = sum(int(row["measure_match_tp"]) for row in rows)
        match_fp = sum(int(row["measure_match_fp"]) for row in rows)
        match_fn = sum(int(row["measure_match_fn"]) for row in rows)
        summary_rows.append(
            {
                "variant": variant,
                "score": score_name,
                "pages": len(rows),
                "pred_measure_count": pred_total,
                "gt_measure_count": gt_total,
                "measure_delta": pred_total - gt_total,
                "measure_abs_delta_sum": abs_total,
                "pages_with_count_delta": pages_with_delta,
                "measure_match_tp": match_tp,
                "measure_match_fp": match_fp,
                "measure_match_fn": match_fn,
                "measure_match_precision": match_tp / (match_tp + match_fp)
                if match_tp + match_fp
                else 0.0,
                "measure_match_recall": match_tp / (match_tp + match_fn)
                if match_tp + match_fn
                else 0.0,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "measure_count_per_page.csv", per_page_rows)
    write_csv(args.output_dir / "measure_count_summary.csv", summary_rows)
    write_csv(
        args.output_dir / "measure_count_delta_pages.csv",
        [row for row in per_page_rows if int(row["measure_abs_delta"]) > 0],
    )
    write_csv(args.output_dir / "missing_inputs.csv", missing_rows)
    write_review_markdown(
        args.output_dir / "measure_count_review.md",
        summary_rows,
        [row for row in per_page_rows if int(row["measure_abs_delta"]) > 0],
    )
    print(f"Wrote {args.output_dir / 'measure_count_summary.csv'}")
    print(f"Missing rows: {len(missing_rows)}")


if __name__ == "__main__":
    main()
