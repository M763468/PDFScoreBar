#!/usr/bin/env python3
"""Evaluate evaluation2 full-run detection outputs and render residuals."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)

Box = tuple[int, int, int, int]


LAYER_FILES = {
    "filtered_cnn_json": "pipeline2_no_peak_filtered_cnn.json",
    "scored_json": "pipeline2_no_peak_scored.json",
    "probe_candidates": "pipeline2_no_peak_candidates.json",
}


def load_json(path: Path) -> Any:
    with path.open("r") as handle:
        return json.load(handle)


def load_gt_boxes(path: Path) -> list[Box]:
    boxes: list[Box] = []
    for item in load_json(path):
        loc = None
        if isinstance(item, list):
            loc = item[:4]
        elif isinstance(item, dict):
            loc = item.get("barline_location") or item.get("box") or item.get("bbox")
        if loc and len(loc) == 4:
            boxes.append(tuple(int(v) for v in loc))
    return boxes


def boxes_from_records(records: Iterable[Any], threshold: float | None = None) -> list[Box]:
    boxes: list[Box] = []
    for item in records:
        loc = None
        score = None
        if isinstance(item, list):
            loc = item[:4]
        elif isinstance(item, dict):
            loc = item.get("bbox") or item.get("barline_location") or item.get("box")
            score = item.get("score")
        if threshold is not None and score is not None and float(score) < threshold:
            continue
        if loc and len(loc) == 4:
            boxes.append(tuple(int(v) for v in loc))
    return boxes


def score_for_box(records: Iterable[Any], target: Box) -> float | None:
    for item in records:
        if not isinstance(item, dict):
            continue
        loc = item.get("bbox") or item.get("barline_location") or item.get("box")
        if loc and tuple(int(v) for v in loc[:4]) == target and "score" in item:
            return float(item["score"])
    return None


def find_page_dir(run_dir: Path, run_id: str, page: str) -> Path | None:
    probe_scan = run_dir / "intermediate" / "probe_scan"
    expected = probe_scan / f"eval2_{run_id}_{page}"
    if expected.exists():
        return expected
    matches = sorted(probe_scan.glob(f"*_{page}"))
    return matches[0] if matches else None


def find_gt_file(gt_root: Path, score: str, page: str) -> Path | None:
    base = gt_root / score / page
    candidates = sorted(base.glob("boxes_sorted*.json"), reverse=True)
    return candidates[0] if candidates else None


def best_detector_score(
    scored_records: list[Any],
    gt_box: Box,
    *,
    eval_rule: str,
    vov_threshold: float,
    xdist_threshold: float,
) -> float | None:
    best: float | None = None
    for record in scored_records:
        if not isinstance(record, dict):
            continue
        loc = record.get("bbox") or record.get("barline_location") or record.get("box")
        if not loc:
            continue
        pred = tuple(int(v) for v in loc[:4])
        if is_barline_match(
            pred,
            gt_box,
            eval_rule,
            vov_threshold=vov_threshold,
            xdist_threshold=xdist_threshold,
        ):
            score = float(record.get("score", 0.0))
            best = score if best is None else max(best, score)
    return best


def draw_box(image: Any, box: Box, color: tuple[int, int, int], label: str) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
    cv2.putText(
        image,
        label,
        (x1, max(0, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
        cv2.LINE_AA,
    )


def save_crop(
    image: Any,
    box: Box,
    output_path: Path,
    *,
    color: tuple[int, int, int],
    label: str,
    pad_x: int,
    pad_y: int,
) -> None:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    left = max(0, cx - pad_x)
    right = min(width, cx + pad_x)
    top = max(0, cy - pad_y)
    bottom = min(height, cy + pad_y)
    crop = image[top:bottom, left:right].copy()
    local_box = (x1 - left, y1 - top, x2 - left, y2 - top)
    draw_box(crop, local_box, color, label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), crop)


def render_visuals(
    image_path: Path,
    output_dir: Path,
    score: str,
    page: str,
    gt_boxes: list[Box],
    pred_boxes: list[Box],
    match_result: Any,
    scored_records: list[Any],
    max_crops_per_type: int,
) -> dict[str, int]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return {"overlays": 0, "fp_crops": 0, "fn_crops": 0}

    fp_indices = list(match_result.false_positive_indices)
    fn_indices = list(match_result.false_negative_indices)
    if not fp_indices and not fn_indices:
        return {"overlays": 0, "fp_crops": 0, "fn_crops": 0}

    overlay = image.copy()
    for match in match_result.matches:
        draw_box(overlay, pred_boxes[match.pred_index], (0, 180, 0), f"TP{match.pred_index}")
    for pred_idx in fp_indices:
        draw_box(overlay, pred_boxes[pred_idx], (0, 0, 255), f"FP{pred_idx}")
    for gt_idx in fn_indices:
        draw_box(overlay, gt_boxes[gt_idx], (255, 0, 255), f"FN{gt_idx}")

    blended = cv2.addWeighted(overlay, 0.65, image, 0.35, 0.0)
    overlay_path = output_dir / "overlays" / score / f"{page}_tp_fp_fn_overlay.png"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(overlay_path), blended)

    fp_count = 0
    for pred_idx in fp_indices[:max_crops_per_type]:
        box = pred_boxes[pred_idx]
        score_value = score_for_box(scored_records, box)
        suffix = f"_score{score_value:.3f}" if score_value is not None else ""
        save_crop(
            image,
            box,
            output_dir / "fp_crops" / score / f"{page}_FP_pred{pred_idx}{suffix}.png",
            color=(0, 0, 255),
            label=f"FP {pred_idx}",
            pad_x=150,
            pad_y=300,
        )
        fp_count += 1

    fn_count = 0
    for gt_idx in fn_indices[:max_crops_per_type]:
        save_crop(
            image,
            gt_boxes[gt_idx],
            output_dir / "fn_crops" / score / f"{page}_FN_gt{gt_idx}.png",
            color=(255, 0, 255),
            label=f"FN {gt_idx}",
            pad_x=150,
            pad_y=300,
        )
        fn_count += 1

    return {"overlays": 1, "fp_crops": fp_count, "fn_crops": fn_count}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--score-thresholds", type=float, nargs="+", default=[0.08, 0.1, 0.5])
    parser.add_argument("--eval-rule", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--render-layer", default="filtered_cnn_json")
    parser.add_argument("--max-crops-per-type", type=int, default=200)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    per_page_rows: list[dict[str, Any]] = []
    residual_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    visual_counts = {"overlays": 0, "fp_crops": 0, "fn_crops": 0}

    for item in manifest:
        score_name = item["score"]
        run_id = item["run_id"]
        run_dir = args.run_root / run_id
        for page in item["pages"]:
            page_dir = find_page_dir(run_dir, run_id, page)
            gt_path = find_gt_file(args.gt_root, score_name, page)
            image_path = args.images_root / score_name / f"{page}.png"
            if page_dir is None or gt_path is None or not image_path.exists():
                missing_rows.append(
                    {
                        "score": score_name,
                        "page": page,
                        "run_id": run_id,
                        "page_dir": str(page_dir) if page_dir else "",
                        "gt_path": str(gt_path) if gt_path else "",
                        "image_path": str(image_path),
                    }
                )
                continue

            gt_boxes = load_gt_boxes(gt_path)
            scored_path = page_dir / LAYER_FILES["scored_json"]
            scored_records = load_json(scored_path) if scored_path.exists() else []

            layer_variants: list[tuple[str, str, Path, float | None]] = [
                (
                    "filtered_cnn_json",
                    "filtered",
                    page_dir / LAYER_FILES["filtered_cnn_json"],
                    None,
                ),
                ("probe_candidates", "all", page_dir / LAYER_FILES["probe_candidates"], None),
            ]
            layer_variants.extend(
                ("scored_json", f"{threshold:g}", scored_path, threshold)
                for threshold in args.score_thresholds
            )

            for layer, threshold_label, json_path, threshold in layer_variants:
                if not json_path.exists():
                    missing_rows.append(
                        {
                            "score": score_name,
                            "page": page,
                            "run_id": run_id,
                            "page_dir": str(page_dir),
                            "gt_path": str(gt_path),
                            "image_path": str(image_path),
                            "missing_json": str(json_path),
                        }
                    )
                    continue

                records = load_json(json_path)
                pred_boxes = boxes_from_records(records, threshold=threshold)
                match_result = greedy_barline_match(
                    pred_boxes,
                    gt_boxes,
                    rule_name=args.eval_rule,
                    vov_threshold=args.vov_threshold,
                    xdist_threshold=args.xdist_threshold,
                )

                fn_cnn = 0
                fn_det = 0
                for gt_idx in match_result.false_negative_indices:
                    best_score = best_detector_score(
                        scored_records,
                        gt_boxes[gt_idx],
                        eval_rule=args.eval_rule,
                        vov_threshold=args.vov_threshold,
                        xdist_threshold=args.xdist_threshold,
                    )
                    if best_score is None:
                        fn_det += 1
                    else:
                        fn_cnn += 1

                per_page_rows.append(
                    {
                        "layer": layer,
                        "threshold": threshold_label,
                        "score": score_name,
                        "page": page,
                        "tp": len(match_result.matches),
                        "fp": len(match_result.false_positive_indices),
                        "fn_total": len(match_result.false_negative_indices),
                        "fn_cnn": fn_cnn,
                        "fn_det": fn_det,
                        "soft_matches": len(match_result.soft_matches),
                        "gt_count": len(gt_boxes),
                        "pred_count": len(pred_boxes),
                        "json_path": str(json_path),
                    }
                )

                for pred_idx in match_result.false_positive_indices:
                    box = pred_boxes[pred_idx]
                    residual_rows.append(
                        {
                            "type": "FP",
                            "layer": layer,
                            "threshold": threshold_label,
                            "score": score_name,
                            "page": page,
                            "index": pred_idx,
                            "bbox": list(box),
                            "cnn_score": score_for_box(scored_records, box),
                            "nearest_gt_xdist": min(
                                (center_distance_x(box, gt) for gt in gt_boxes), default=None
                            ),
                        }
                    )
                for gt_idx in match_result.false_negative_indices:
                    box = gt_boxes[gt_idx]
                    best_score = best_detector_score(
                        scored_records,
                        box,
                        eval_rule=args.eval_rule,
                        vov_threshold=args.vov_threshold,
                        xdist_threshold=args.xdist_threshold,
                    )
                    residual_rows.append(
                        {
                            "type": "FN_cnn" if best_score is not None else "FN_det",
                            "layer": layer,
                            "threshold": threshold_label,
                            "score": score_name,
                            "page": page,
                            "index": gt_idx,
                            "bbox": list(box),
                            "cnn_score": best_score,
                            "nearest_gt_xdist": None,
                        }
                    )

                if layer == args.render_layer and threshold_label == "filtered":
                    counts = render_visuals(
                        image_path,
                        args.output_dir / "visuals",
                        score_name,
                        page,
                        gt_boxes,
                        pred_boxes,
                        match_result,
                        scored_records,
                        args.max_crops_per_type,
                    )
                    for key, value in counts.items():
                        visual_counts[key] += value

    summary: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "pages": 0,
            "tp": 0,
            "fp": 0,
            "fn_total": 0,
            "fn_cnn": 0,
            "fn_det": 0,
            "gt_count": 0,
            "pred_count": 0,
        }
    )
    for row in per_page_rows:
        key = (row["layer"], row["threshold"], row["score"])
        bucket = summary[key]
        bucket["pages"] += 1
        for field in ("tp", "fp", "fn_total", "fn_cnn", "fn_det", "gt_count", "pred_count"):
            bucket[field] += int(row[field])

    summary_rows: list[dict[str, Any]] = []
    for (layer, threshold, score), values in sorted(summary.items()):
        tp = values["tp"]
        fp = values["fp"]
        gt_count = values["gt_count"]
        summary_rows.append(
            {
                "layer": layer,
                "threshold": threshold,
                "score": score,
                **values,
                "recall": tp / gt_count if gt_count else 0.0,
                "precision": tp / (tp + fp) if tp + fp else 0.0,
            }
        )

    for layer, threshold in sorted({(r["layer"], r["threshold"]) for r in summary_rows}):
        rows = [r for r in summary_rows if r["layer"] == layer and r["threshold"] == threshold]
        totals = defaultdict(int)
        for row in rows:
            for field in (
                "pages",
                "tp",
                "fp",
                "fn_total",
                "fn_cnn",
                "fn_det",
                "gt_count",
                "pred_count",
            ):
                totals[field] += int(row[field])
        tp = totals["tp"]
        fp = totals["fp"]
        gt_count = totals["gt_count"]
        summary_rows.append(
            {
                "layer": layer,
                "threshold": threshold,
                "score": "GLOBAL_TOTAL",
                **totals,
                "recall": tp / gt_count if gt_count else 0.0,
                "precision": tp / (tp + fp) if tp + fp else 0.0,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "per_page_stats.csv", per_page_rows)
    write_csv(args.output_dir / "summary_by_layer.csv", summary_rows)
    write_csv(args.output_dir / "residuals.csv", residual_rows)
    write_csv(args.output_dir / "missing_inputs.csv", missing_rows)
    (args.output_dir / "visual_summary.json").write_text(
        json.dumps(visual_counts, indent=2, sort_keys=True)
    )

    print(f"Wrote {args.output_dir / 'summary_by_layer.csv'}")
    print(f"Wrote {args.output_dir / 'per_page_stats.csv'}")
    print(f"Wrote {args.output_dir / 'residuals.csv'}")
    print(f"Visuals: {visual_counts}")
    if missing_rows:
        print(
            f"Missing inputs: {len(missing_rows)} rows in {args.output_dir / 'missing_inputs.csv'}"
        )


if __name__ == "__main__":
    main()
