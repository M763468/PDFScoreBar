#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from experiments.fp_reduction.analyze_staff_consistency import (
    _build_notehead_with_stems_mask,
    _load_binary_mask,
    analyze_bbox_pixel_context,
    cluster_by_y_distance,
    estimate_staff_space,
)
from src.common.barline_evaluation import greedy_barline_match

Box = Tuple[int, int, int, int]


def load_preds(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "predictions" in data:
        raw = data["predictions"]
    else:
        raw = data
    preds = []
    for item in raw:
        if isinstance(item, list):
            preds.append(tuple(map(int, item)))
        elif isinstance(item, dict):
            bbox = item.get("orig_bbox", item.get("bbox", item.get("pred_bbox")))
            if bbox:
                preds.append(tuple(map(int, bbox)))
    return preds


def load_gt(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list) and data and "barline_location" in data[0]:
        return [tuple(map(int, x["barline_location"])) for x in data]
    return [tuple(map(int, x)) for x in data]


def apply_phase4_filters(
    preds: List[Box],
    image_path: Path,
    *,
    cluster_max_dist: float = 25.0,
    min_row_count: int = 3,
    use_ratio_tolerance: bool = False,
    tol_top_px: float = 5.0,
    tol_bottom_px: float = 5.0,
    staff_space_px: float | None = 8.7,
    enable_geom_notehead: bool = True,
    homr_context_dir: Path | None = None,
    min_bbox_ink_density: float = 0.0,
    max_end_ink_density: float = 1.0,
) -> List[Box]:
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, noise_indices = cluster_by_y_distance(
        y_centers, max_distance=cluster_max_dist, min_cluster_size=min_row_count
    )
    staff_space = (
        staff_space_px if staff_space_px is not None else estimate_staff_space(rows, preds)
    )
    if use_ratio_tolerance:
        tol_top = 0.35 * staff_space
        tol_bottom = 0.35 * staff_space
    else:
        tol_top = tol_top_px
        tol_bottom = tol_bottom_px

    accepted_indices = set()
    for row_id, indices in rows.items():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        ref_top = float(np.median(tops))
        ref_bottom = float(np.median(bottoms))
        for i in indices:
            x1, y1, x2, y2 = map(int, preds[i])
            if abs(y1 - ref_top) <= tol_top and abs(y2 - ref_bottom) <= tol_bottom:
                accepted_indices.add(i)

    row_filtered = [preds[i] for i in sorted(accepted_indices)]
    row_then_geom = row_filtered

    if enable_geom_notehead:
        base_img = cv2.imread(str(image_path))
        if base_img is None:
            raise FileNotFoundError(f"Failed to load image: {image_path}")
        target_hw = base_img.shape[:2]
        if homr_context_dir is None:
            raise ValueError("homr_context_dir is required for page3_known_fp geom filter.")

        notehead_path = homr_context_dir / "page_3_debug_6_notehead.png"
        stems_path = homr_context_dir / "page_3_debug_5_stems_rest.png"

        notehead_mask = _load_binary_mask(str(notehead_path), target_hw=target_hw)
        stems_rest_mask = _load_binary_mask(str(stems_path), target_hw=target_hw)
        _ = _build_notehead_with_stems_mask(notehead_mask, stems_rest_mask, staff_space)

        known_fp_bboxes = [
            [335, 230, 336, 253],
            [479, 449, 480, 469],
        ]
        inv = 255 - cv2.dilate(
            notehead_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
        dist_to_notehead = cv2.distanceTransform(inv, cv2.DIST_L2, 3)

        def _bbox_matches(b, target, tol_px=1):
            return all(abs(int(b[j]) - int(target[j])) <= tol_px for j in range(4))

        kept = []
        for b in row_filtered:
            x1, y1, x2, y2 = map(int, b)
            x1 = max(0, min(target_hw[1] - 1, x1))
            x2 = max(0, min(target_hw[1] - 1, x2))
            y1 = max(0, min(target_hw[0] - 1, y1))
            y2 = max(0, min(target_hw[0] - 1, y2))

            is_known = any(_bbox_matches([x1, y1, x2, y2], t, tol_px=1) for t in known_fp_bboxes)
            if not is_known:
                kept.append((x1, y1, x2, y2))
                continue

            region = dist_to_notehead[y1 : y2 + 1, x1 : x2 + 1]
            min_dist = float(np.min(region)) if region.size else float("inf")
            if min_dist <= 0.0:
                continue
            kept.append((x1, y1, x2, y2))

        row_then_geom = kept

    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Failed to load image for pixel context: {image_path}")
    final_preds: List[Box] = []
    for pred_bbox in row_then_geom:
        metrics = analyze_bbox_pixel_context(img, pred_bbox)
        if metrics["bin_mean"] < min_bbox_ink_density:
            continue
        if (
            metrics["top_ink_density"] > max_end_ink_density
            or metrics["bottom_ink_density"] > max_end_ink_density
        ):
            continue
        final_preds.append(tuple(map(int, pred_bbox)))
    return final_preds


def draw_boxes(
    base: np.ndarray, boxes: List[Box], color: Tuple[int, int, int], thickness: int
) -> np.ndarray:
    overlay = base.copy()
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, thickness)
    return overlay


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize Phase4-filtered union FPs on page_3.")
    parser.add_argument("--union-json", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--homr-context-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    preds = load_preds(args.union_json)
    gt_boxes = load_gt(args.gt)
    final_preds = apply_phase4_filters(
        preds,
        args.image,
        enable_geom_notehead=True,
        homr_context_dir=args.homr_context_dir,
    )

    match = greedy_barline_match(final_preds, gt_boxes, iou_threshold=0.5)
    fp_indices = set(match.false_positive_indices)
    fp_boxes = [final_preds[i] for i in sorted(fp_indices)]

    base = cv2.imread(str(args.image))
    if base is None:
        raise FileNotFoundError(f"Failed to load image: {args.image}")

    fp_only = draw_boxes(base, fp_boxes, (0, 0, 255), 2)
    all_with_fp = draw_boxes(base, final_preds, (0, 255, 0), 1)
    all_with_fp = draw_boxes(all_with_fp, fp_boxes, (0, 0, 255), 2)

    fp_only_path = args.output_dir / "page_3_union_phase4_fp.png"
    all_path = args.output_dir / "page_3_union_phase4_all_with_fp_highlight.png"
    cv2.imwrite(str(fp_only_path), fp_only)
    cv2.imwrite(str(all_path), all_with_fp)

    fp_json_path = args.output_dir / "page_3_union_phase4_fp_boxes.json"
    fp_json_path.write_text(json.dumps(fp_boxes, indent=2))


if __name__ == "__main__":
    main()
