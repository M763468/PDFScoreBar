#!/usr/bin/env python3
"""Analyze notehead filter behavior for remaining FP and notehead-filtered FN."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
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
        out: list[Box] = []
        for item in data:
            if isinstance(item, list) and len(item) == 4:
                out.append(tuple(map(int, item)))
        return out
    return []


def load_notehead_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Missing notehead mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return (mask > 0).astype(np.uint8)


def endpoint_overlap_ratio(
    notehead_mask: np.ndarray,
    box: Box,
    rx: int,
    ry: int,
) -> float:
    h, w = notehead_mask.shape[:2]
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, int(x1)))
    x2 = max(0, min(w - 1, int(x2)))
    y1 = max(0, min(h - 1, int(y1)))
    y2 = max(0, min(h - 1, int(y2)))
    xm = (x1 + x2) // 2
    tx1, tx2 = max(0, xm - rx), min(w, xm + rx + 1)
    ty1, ty2 = max(0, y1 - ry), min(h, y1 + ry + 1)
    bx1, bx2 = max(0, xm - rx), min(w, xm + rx + 1)
    by1, by2 = max(0, y2 - ry), min(h, y2 + ry + 1)
    top_region = notehead_mask[ty1:ty2, tx1:tx2]
    bot_region = notehead_mask[by1:by2, bx1:bx2]
    total_area = int(top_region.size + bot_region.size)
    total_notehead = int(np.count_nonzero(top_region) + np.count_nonzero(bot_region))
    return 0.0 if total_area == 0 else total_notehead / total_area


def endpoint_overlap_detail(
    notehead_mask: np.ndarray,
    box: Box,
    rx: int,
    ry: int,
) -> dict:
    h, w = notehead_mask.shape[:2]
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, int(x1)))
    x2 = max(0, min(w - 1, int(x2)))
    y1 = max(0, min(h - 1, int(y1)))
    y2 = max(0, min(h - 1, int(y2)))
    xm = (x1 + x2) // 2
    tx1, tx2 = max(0, xm - rx), min(w, xm + rx + 1)
    ty1, ty2 = max(0, y1 - ry), min(h, y1 + ry + 1)
    bx1, bx2 = max(0, xm - rx), min(w, xm + rx + 1)
    by1, by2 = max(0, y2 - ry), min(h, y2 + ry + 1)
    top_region = notehead_mask[ty1:ty2, tx1:tx2]
    bot_region = notehead_mask[by1:by2, bx1:bx2]
    notehead_pixels_top = int(np.count_nonzero(top_region))
    notehead_pixels_bottom = int(np.count_nonzero(bot_region))
    total_area = int(top_region.size + bot_region.size)
    total_notehead = notehead_pixels_top + notehead_pixels_bottom
    overlap_ratio = 0.0 if total_area == 0 else total_notehead / total_area
    return {
        "overlap_ratio": float(overlap_ratio),
        "total_area": total_area,
        "notehead_pixels": total_notehead,
        "top_region": [tx1, ty1, tx2, ty2],
        "bottom_region": [bx1, by1, bx2, by2],
    }


def draw_boxes(img: np.ndarray, boxes: Iterable[Box], color: tuple[int, int, int], thickness: int) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--analysis-root", type=Path, required=True, help="postfilter_analysis_v3 path")
    parser.add_argument("--overlay-alpha", type=float, default=0.35)
    parser.add_argument("--mask-dilate", type=int, default=0)
    parser.add_argument("--override-threshold", type=float, default=-1.0)
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
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_6_notehead.png",
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
        if args.mask_dilate > 0:
            kernel = np.ones((args.mask_dilate, args.mask_dilate), dtype=np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)
        geom_debug_path = page_dir / "geom_debug.json"
        config = json.loads(geom_debug_path.read_text())["config"]
        rx = int(config["endpoint_radius_px"]["x"])
        ry = int(config["endpoint_radius_px"]["y"])
        threshold = float(config["threshold"]) if args.override_threshold < 0 else args.override_threshold

        fp_boxes = load_boxes(page_dir / "fp_boxes.json")
        fn_report_path = args.analysis_root / f"{page.name}_fn_report.json"
        notehead_fn = []
        if fn_report_path.exists():
            fn_report = json.loads(fn_report_path.read_text())
            notehead_fn = [
                tuple(item["bbox"]) for item in fn_report if item.get("reason") == "notehead_filtered"
            ]

        fp_stats = []
        for idx, box in enumerate(fp_boxes):
            detail = endpoint_overlap_detail(mask, box, rx, ry)
            fp_stats.append({"index": idx, "bbox": list(box), **detail})
        fn_stats = []
        for idx, box in enumerate(notehead_fn):
            detail = endpoint_overlap_detail(mask, box, rx, ry)
            fn_stats.append({"index": idx, "bbox": list(box), **detail})

        overlay = base_img.copy()
        mask_vis = cv2.applyColorMap((mask * 255).astype(np.uint8), cv2.COLORMAP_OCEAN)
        alpha = min(max(args.overlay_alpha, 0.0), 0.9)
        overlay = cv2.addWeighted(mask_vis, alpha, overlay, 1 - alpha, 0.0)
        draw_boxes(overlay, fp_boxes, (0, 0, 255), 2)
        draw_boxes(overlay, notehead_fn, (255, 0, 255), 3)
        for item in fn_stats:
            tx1, ty1, tx2, ty2 = item["top_region"]
            bx1, by1, bx2, by2 = item["bottom_region"]
            cv2.rectangle(overlay, (tx1, ty1), (tx2, ty2), (0, 255, 255), 1)
            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), (0, 255, 255), 1)
        overlay_path = out_root / f"{page.name}_notehead_overlay.png"
        cv2.imwrite(str(overlay_path), overlay)

        endpoint_overlay = base_img.copy()
        for item in fp_stats:
            tx1, ty1, tx2, ty2 = item["top_region"]
            bx1, by1, bx2, by2 = item["bottom_region"]
            cv2.rectangle(endpoint_overlay, (tx1, ty1), (tx2, ty2), (0, 0, 255), 1)
            cv2.rectangle(endpoint_overlay, (bx1, by1), (bx2, by2), (0, 0, 255), 1)
        for item in fn_stats:
            tx1, ty1, tx2, ty2 = item["top_region"]
            bx1, by1, bx2, by2 = item["bottom_region"]
            cv2.rectangle(endpoint_overlay, (tx1, ty1), (tx2, ty2), (0, 255, 255), 2)
            cv2.rectangle(endpoint_overlay, (bx1, by1), (bx2, by2), (0, 255, 255), 2)
        endpoint_overlay_path = out_root / f"{page.name}_endpoint_windows.png"
        cv2.imwrite(str(endpoint_overlay_path), endpoint_overlay)

        (out_root / f"{page.name}_fp_notehead_stats.json").write_text(json.dumps(fp_stats, indent=2))
        (out_root / f"{page.name}_fn_notehead_stats.json").write_text(json.dumps(fn_stats, indent=2))
        summary[page.name] = {
            "fp_count": len(fp_stats),
            "fn_notehead_count": len(fn_stats),
            "threshold": threshold,
            "mask_dilate": args.mask_dilate,
            "fp_ratio_ge_0.3": sum(1 for r in fp_stats if r["overlap_ratio"] >= 0.3),
            "fn_ratio_ge_0.3": sum(1 for r in fn_stats if r["overlap_ratio"] >= 0.3),
            "fp_ratio_ge_threshold": sum(1 for r in fp_stats if r["overlap_ratio"] >= threshold),
            "fn_ratio_ge_threshold": sum(1 for r in fn_stats if r["overlap_ratio"] >= threshold),
        }

    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
