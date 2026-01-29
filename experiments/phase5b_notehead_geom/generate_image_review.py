#!/usr/bin/env python3
"""
Generate image-based review artifacts for Phase 5b2 (no detector reruns).

Default style: one image per box (cropped with context).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]

Box = Tuple[int, int, int, int]


def load_boxes(path: Path) -> List[Dict]:
    return json.loads(path.read_text())


def load_gt(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list) and data and "barline_location" in data[0]:
        return [tuple(map(int, x["barline_location"])) for x in data]
    return [tuple(map(int, x)) for x in data]


def iou(box_a: Box, box_b: Box) -> float:
    xA = max(box_a[0], box_b[0])
    yA = max(box_a[1], box_b[1])
    xB = min(box_a[2], box_b[2])
    yB = min(box_a[3], box_b[3])
    inter_area = max(0, xB - xA) * max(0, yB - yA)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    denom = area_a + area_b - inter_area
    return inter_area / denom if denom > 0 else 0.0


def margin_class(box: Box, width: int, band_px: int) -> str:
    cx = (box[0] + box[2]) / 2
    if cx <= band_px:
        return "left"
    if cx >= width - band_px:
        return "right"
    return "interior"


def apply_margin_bands(base, band_px: int):
    overlay = base.copy()
    h, w = base.shape[:2]
    band_color = (80, 80, 80)
    alpha = 0.25
    left = overlay[:, :band_px]
    right = overlay[:, w - band_px :]
    band = (np.array(band_color, dtype="float32") * alpha).reshape(1, 1, 3)
    left[:] = (left * (1 - alpha) + band).astype("uint8")
    right[:] = (right * (1 - alpha) + band).astype("uint8")
    overlay[:, :band_px] = left
    overlay[:, w - band_px :] = right
    return overlay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--overlay-data-root", type=Path, required=True)
    parser.add_argument("--style", choices=["box", "page"], default="box")
    parser.add_argument("--crop-pad", type=int, default=80)
    args = parser.parse_args()

    review_root = args.review_root
    (review_root / "classified").mkdir(parents=True, exist_ok=True)

    labels = [
        "tp_same_position",
        "stem_like",
        "text_region",
        "margin_artifact",
        "staff_noise",
        "other",
        "unclear",
    ]
    for label in labels:
        (review_root / "classified" / label).mkdir(parents=True, exist_ok=True)

    readme = [
        "# Manual classification folders",
        "",
        "Move review images into one of these folders:",
    ]
    for label in labels:
        readme.append(f"- {label}")
    readme.append("")
    readme.append("Images left in the root are treated as unclassified.")
    (review_root / "classified" / "README.md").write_text("\n".join(readme) + "\n")

    pages = [
        {
            "name": "page_3",
            "image": REPO_ROOT / "data/evaluation/images/page_3.png",
            "gt": REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json",
        },
        {
            "name": "page_001",
            "image": REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            "gt": REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
        },
        {
            "name": "page_004",
            "image": REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            "gt": REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
        },
        {
            "name": "page_10",
            "image": REPO_ROOT / "data/training/images/page_10.png",
            "gt": REPO_ROOT / "data/training/annotations/page_010/fn_only.json",
        },
        {
            "name": "page_15",
            "image": REPO_ROOT / "data/training/images/page_15.png",
            "gt": REPO_ROOT / "data/training/annotations/page_015/fn_only.json",
        },
    ]

    index_rows = []
    for page in pages:
        boxes_path = args.overlay_data_root / f"{page['name']}_boxes.json"
        boxes = load_boxes(boxes_path)
        unmatched = [b for b in boxes if b["category"] == "final_unmatched"]

        img = cv2.imread(str(page["image"]))
        if img is None:
            raise FileNotFoundError(f"Failed to load image: {page['image']}")
        h, w = img.shape[:2]
        band_px = max(40, int(0.05 * w))
        overlay = apply_margin_bands(img, band_px)

        gt_boxes = load_gt(page["gt"]) if page["name"] == "page_3" else []
        if page["name"] == "page_3":
            for gt in gt_boxes:
                cv2.rectangle(overlay, (gt[0], gt[1]), (gt[2], gt[3]), (255, 0, 255), 1)

        for box in unmatched:
            x1, y1, x2, y2 = box["bbox"]
            box_id = box["id"]
            best_iou = None
            best_x_dist = None
            if page["name"] == "page_3":
                if gt_boxes:
                    best_iou = max(iou(tuple(box["bbox"]), gt) for gt in gt_boxes)
                    cx = (box["bbox"][0] + box["bbox"][2]) / 2
                    best_x_dist = min(abs(cx - (gt[0] + gt[2]) / 2) for gt in gt_boxes)

            margin_band = margin_class(tuple(box["bbox"]), w, band_px)
            if args.style == "page":
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(
                    overlay,
                    box_id,
                    (x1 + 2, max(15, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    1,
                    cv2.LINE_AA,
                )
                filename = f"{page['name']}_unmatched.png"
            else:
                pad = args.crop_pad
                cx1 = max(0, x1 - pad)
                cy1 = max(0, y1 - pad)
                cx2 = min(w, x2 + pad)
                cy2 = min(h, y2 + pad)
                crop = overlay[cy1:cy2, cx1:cx2].copy()
                cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), 3)
                cv2.putText(
                    crop,
                    box_id,
                    (max(2, x1 - cx1 + 2), max(15, y1 - cy1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    1,
                    cv2.LINE_AA,
                )
                filename = f"{page['name']}_{box_id}.png"
                cv2.imwrite(str(review_root / filename), crop)

            index_rows.append(
                {
                    "filename": filename,
                    "page": page["name"],
                    "box_id": box_id,
                    "bbox": box["bbox"],
                    "gt_present": page["name"] == "page_3",
                    "nearest_gt_iou": best_iou,
                    "nearest_gt_x_distance": best_x_dist,
                    "margin_band": margin_band,
                }
            )

        if args.style == "page":
            out_path = review_root / f"{page['name']}_unmatched.png"
            cv2.imwrite(str(out_path), overlay)

    (review_root / "image_index.json").write_text(json.dumps(index_rows, indent=2))


if __name__ == "__main__":
    main()
