#!/usr/bin/env python3
"""Analyze which notehead overlap caused FN after notehead filter."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))
from src.common.barline_evaluation import barline_iou

Box = tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    image: Path
    notehead_mask: Path


def load_boxes(path: Path) -> list[Box]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(map(int, item)) for item in data if isinstance(item, list) and len(item) == 4]
    return []


def load_notehead_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Missing notehead mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return (mask > 0).astype(np.uint8)


def denoise_notehead_mask(mask: np.ndarray, open_kernel: int, min_area: int) -> np.ndarray:
    cleaned = (mask > 0).astype(np.uint8)
    if open_kernel and open_kernel > 1:
        kernel = np.ones((open_kernel, open_kernel), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    if min_area and min_area > 0:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
        filtered = np.zeros_like(cleaned)
        for label in range(1, num_labels):
            if stats[label, cv2.CC_STAT_AREA] >= min_area:
                filtered[labels == label] = 1
        cleaned = filtered
    return cleaned


def filter_notehead_components(
    mask: np.ndarray,
    max_aspect_ratio: float,
    min_height_px: int,
    max_width_px: int,
) -> np.ndarray:
    if max_aspect_ratio <= 0:
        return mask
    binary = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary)
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        if min_height_px and h < min_height_px:
            filtered[labels == label] = 1
            continue
        if max_width_px and w > max_width_px:
            filtered[labels == label] = 1
            continue
        aspect = h / max(w, 1)
        if aspect <= max_aspect_ratio:
            filtered[labels == label] = 1
    return filtered


def endpoint_windows(box: Box, rx: int, ry: int, shape: tuple[int, int]) -> tuple[Box, Box]:
    h, w = shape[:2]
    x1, y1, x2, y2 = map(int, box)
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w - 1, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h - 1, y2))
    xm = (x1 + x2) // 2
    tx1, tx2 = max(0, xm - rx), min(w - 1, xm + rx)
    ty1, ty2 = max(0, y1 - ry), min(h - 1, y1 + ry)
    bx1, bx2 = max(0, xm - rx), min(w - 1, xm + rx)
    by1, by2 = max(0, y2 - ry), min(h - 1, y2 + ry)
    return (tx1, ty1, tx2, ty2), (bx1, by1, bx2, by2)


def endpoint_overlap(mask: np.ndarray, box: Box, rx: int, ry: int) -> float:
    top, bot = endpoint_windows(box, rx, ry, mask.shape[:2])
    tx1, ty1, tx2, ty2 = top
    bx1, by1, bx2, by2 = bot
    top_region = mask[ty1 : ty2 + 1, tx1 : tx2 + 1]
    bot_region = mask[by1 : by2 + 1, bx1 : bx2 + 1]
    total_area = int(top_region.size + bot_region.size)
    total_notehead = int(np.count_nonzero(top_region) + np.count_nonzero(bot_region))
    return 0.0 if total_area == 0 else total_notehead / total_area


def draw_boxes(
    img: np.ndarray, boxes: Iterable[Box], color: tuple[int, int, int], thickness: int
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def best_match(target: Box, boxes: Iterable[Box]) -> tuple[Optional[Box], float]:
    best_box = None
    best_score = 0.0
    for box in boxes:
        score = barline_iou(target, box)
        if score > best_score:
            best_score = score
            best_box = box
    return best_box, best_score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--notehead-open-kernel", type=int, default=0)
    parser.add_argument("--notehead-min-area", type=int, default=0)
    parser.add_argument("--notehead-max-aspect", type=float, default=0.0)
    parser.add_argument("--notehead-min-height", type=int, default=0)
    parser.add_argument("--notehead-max-width", type=int, default=0)
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            notehead_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            notehead_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            notehead_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            notehead_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_6_notehead.png",
        ),
    ]

    out_root = args.output_root
    out_root.mkdir(parents=True, exist_ok=True)
    summary = {}

    for page in pages:
        page_dir = args.eval_root / "per_page" / page.name
        if not page_dir.exists():
            continue
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Missing image: {page.image}")
        mask = load_notehead_mask(page.notehead_mask, base_img.shape[:2])
        mask = denoise_notehead_mask(mask, args.notehead_open_kernel, args.notehead_min_area)
        mask = filter_notehead_components(
            mask,
            args.notehead_max_aspect,
            args.notehead_min_height,
            args.notehead_max_width,
        )
        geom_debug = json.loads((page_dir / "geom_debug.json").read_text())["config"]
        rx = int(geom_debug["endpoint_radius_px"]["x"])
        ry = int(geom_debug["endpoint_radius_px"]["y"])
        threshold = float(geom_debug["threshold"])

        fn_report_path = args.analysis_root / f"{page.name}_fn_report.json"
        if not fn_report_path.exists():
            continue
        fn_report = json.loads(fn_report_path.read_text())
        notehead_fn = [item for item in fn_report if item.get("reason") == "notehead_filtered"]
        end_row = load_boxes(page_dir / "end_recovered_row.json")
        end_geom = load_boxes(page_dir / "end_recovered_geom.json")
        rejected_debug = json.loads((page_dir / "end_recovered_geom_debug.json").read_text())
        rejected_list = rejected_debug.get("rejected", [])

        records = []
        for item in notehead_fn:
            fn_box = tuple(item["bbox"])
            cand_box, score = best_match(fn_box, end_row)
            if cand_box is None or score < args.iou_threshold:
                records.append(
                    {
                        "fn_bbox": list(fn_box),
                        "status": "no_candidate_match",
                        "best_iou": score,
                    }
                )
                continue
            rej_box = None
            rej_score = 0.0
            rej_info = None
            for rej in rejected_list:
                rbox = tuple(rej["bbox"])
                rscore = barline_iou(fn_box, rbox)
                if rscore > rej_score:
                    rej_score = rscore
                    rej_box = rbox
                    rej_info = rej
            overlap = endpoint_overlap(mask, cand_box, rx, ry)
            geom_box, geom_score = best_match(fn_box, end_geom)
            records.append(
                {
                    "fn_bbox": list(fn_box),
                    "candidate_bbox": list(cand_box),
                    "best_iou": score,
                    "endpoint_overlap_ratio": overlap,
                    "threshold": threshold,
                    "best_geom_iou": geom_score,
                    "best_geom_bbox": list(geom_box) if geom_box else None,
                    "rejected_bbox": list(rej_box) if rej_box else None,
                    "rejected_iou": rej_score,
                    "rejected_overlap_ratio": rej_info.get("overlap_ratio") if rej_info else None,
                }
            )

        overlay = base_img.copy()
        for rec in records:
            if "candidate_bbox" not in rec:
                continue
            cand = tuple(rec["candidate_bbox"])
            top, bot = endpoint_windows(cand, rx, ry, mask.shape[:2])
            draw_boxes(overlay, [cand], (0, 165, 255), 2)
            draw_boxes(overlay, [top, bot], (0, 255, 255), 1)
            if rec.get("rejected_bbox"):
                rej = tuple(rec["rejected_bbox"])
                draw_boxes(overlay, [rej], (255, 128, 0), 2)
            if rec.get("best_geom_bbox"):
                geom = tuple(rec["best_geom_bbox"])
                draw_boxes(overlay, [geom], (0, 255, 0), 1)
        for rec in records:
            draw_boxes(overlay, [tuple(rec["fn_bbox"])], (255, 0, 255), 2)
        overlay_path = out_root / f"{page.name}_notehead_fn_causes.png"
        cv2.imwrite(str(overlay_path), overlay)

        (out_root / f"{page.name}_notehead_fn_causes.json").write_text(
            json.dumps(records, indent=2)
        )

        # Per-FN crops with notehead mask overlay.
        for idx, rec in enumerate(records):
            if "candidate_bbox" not in rec:
                continue
            cand = tuple(rec["candidate_bbox"])
            x1, y1, x2, y2 = cand
            pad = 40
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(base_img.shape[1] - 1, x2 + pad)
            cy2 = min(base_img.shape[0] - 1, y2 + pad)
            crop = base_img[cy1 : cy2 + 1, cx1 : cx2 + 1].copy()
            mask_crop = (mask[cy1 : cy2 + 1, cx1 : cx2 + 1] * 255).astype(np.uint8)
            mask_vis = cv2.applyColorMap(mask_crop, cv2.COLORMAP_OCEAN)
            crop = cv2.addWeighted(mask_vis, 0.4, crop, 0.6, 0.0)
            top, bot = endpoint_windows(cand, rx, ry, mask.shape[:2])
            # Shift to crop coordinates.
            top = (top[0] - cx1, top[1] - cy1, top[2] - cx1, top[3] - cy1)
            bot = (bot[0] - cx1, bot[1] - cy1, bot[2] - cx1, bot[3] - cy1)
            cand_local = (x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1)
            draw_boxes(crop, [cand_local], (0, 165, 255), 2)
            draw_boxes(crop, [top, bot], (0, 255, 255), 1)
            draw_boxes(
                crop,
                [tuple(v - o for v, o in zip(rec["fn_bbox"], (cx1, cy1, cx1, cy1)))],
                (255, 0, 255),
                2,
            )
            crop_path = out_root / f"{page.name}_fn_{idx:02d}_crop.png"
            cv2.imwrite(str(crop_path), crop)
        summary[page.name] = {
            "fn_notehead_count": len(notehead_fn),
            "with_candidate_match": sum(1 for r in records if "candidate_bbox" in r),
        }

    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
