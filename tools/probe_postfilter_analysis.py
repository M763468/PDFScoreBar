#!/usr/bin/env python3
"""Analyze FN reappearance and remaining FP after post-filters."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.common.barline_evaluation import barline_iou

REPO_ROOT = Path(__file__).resolve().parents[1]
Box = tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    image: Path


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


def match_box(target: Box, boxes: Iterable[Box], thr: float = 0.5) -> bool:
    return any(barline_iou(target, b) >= thr for b in boxes)


def draw_boxes(
    img: np.ndarray, boxes: Iterable[Box], color: tuple[int, int, int], thickness: int
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def summarize_fp(fp_boxes: list[Box], fp_class: list[dict]) -> dict:
    ratios = []
    for rec in fp_class:
        ratios.append(rec.get("barline_mask_ratio", 0.0))
    return {
        "count": len(fp_boxes),
        "barline_mask_ratio_ge_0.5": sum(1 for r in ratios if r >= 0.5),
        "barline_mask_ratio_ge_0.2": sum(1 for r in ratios if r >= 0.2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
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
        fn_boxes = load_boxes(page_dir / "fn_boxes.json")
        fp_boxes = load_boxes(page_dir / "fp_boxes.json")
        end_all = load_boxes(page_dir / "end_recovered.json")
        end_row = load_boxes(page_dir / "end_recovered_row.json")
        end_geom_pre = load_boxes(page_dir / "end_recovered_geom_pre_mask.json")
        end_geom = load_boxes(page_dir / "end_recovered_geom.json")
        fp_class = []
        fp_class_path = page_dir / "fp_classification.json"
        if fp_class_path.exists():
            fp_class = json.loads(fp_class_path.read_text())

        fn_report = []
        for idx, fn in enumerate(fn_boxes):
            found_probe = match_box(fn, end_all, args.iou_threshold)
            kept_row = match_box(fn, end_row, args.iou_threshold)
            kept_geom_pre = match_box(fn, end_geom_pre, args.iou_threshold)
            kept_geom = match_box(fn, end_geom, args.iou_threshold)
            reason = "probe_missing"
            if found_probe and not kept_row:
                reason = "row_filtered"
            elif found_probe and kept_row and not kept_geom_pre:
                reason = "notehead_filtered"
            elif found_probe and kept_row and kept_geom_pre and not kept_geom:
                reason = "barline_mask_filtered"
            elif found_probe and kept_geom:
                reason = "kept_but_missed_match"
            fn_report.append(
                {
                    "index": idx,
                    "bbox": list(fn),
                    "found_probe": found_probe,
                    "kept_row": kept_row,
                    "kept_geom": kept_geom,
                    "reason": reason,
                }
            )

        removed_by_row = [b for b in end_all if not match_box(b, end_row, args.iou_threshold)]
        removed_by_notehead = [b for b in end_row if not match_box(b, end_geom, args.iou_threshold)]

        overlay = base_img.copy()
        draw_boxes(overlay, end_all, (90, 200, 90), 1)
        draw_boxes(overlay, removed_by_row, (255, 140, 0), 2)
        draw_boxes(overlay, removed_by_notehead, (0, 128, 255), 2)
        draw_boxes(overlay, fn_boxes, (255, 0, 255), 3)
        overlay_path = out_root / f"{page.name}_filter_effects.png"
        cv2.imwrite(str(overlay_path), overlay)

        fp_overlay = base_img.copy()
        draw_boxes(fp_overlay, fp_boxes, (0, 0, 255), 2)
        fp_overlay_path = out_root / f"{page.name}_fp_remaining.png"
        cv2.imwrite(str(fp_overlay_path), fp_overlay)

        summary[page.name] = {
            "fn_count": len(fn_boxes),
            "fn_reasons": {
                "row_filtered": sum(1 for r in fn_report if r["reason"] == "row_filtered"),
                "notehead_filtered": sum(
                    1 for r in fn_report if r["reason"] == "notehead_filtered"
                ),
                "barline_mask_filtered": sum(
                    1 for r in fn_report if r["reason"] == "barline_mask_filtered"
                ),
                "probe_missing": sum(1 for r in fn_report if r["reason"] == "probe_missing"),
                "kept_but_missed_match": sum(
                    1 for r in fn_report if r["reason"] == "kept_but_missed_match"
                ),
            },
            "fp_summary": summarize_fp(fp_boxes, fp_class),
        }
        (out_root / f"{page.name}_fn_report.json").write_text(json.dumps(fn_report, indent=2))

    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
