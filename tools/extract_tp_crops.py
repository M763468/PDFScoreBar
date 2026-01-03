#!/usr/bin/env python3
import json
import cv2
import os
from pathlib import Path

def extract_crops():
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / "logs/tp_crops"
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = [
        {
            "name": "page_001",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json"
        },
        {
            "name": "page_3",
            "image": repo_root / "logs/homr_eval/baseline_for_hybrid/page_3/page_3.png",
            "gt": repo_root / "data/evaluation/annotations/page_003/boxes_sorted.json"
        },
        {
            "name": "page_004",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json"
        },
        {
            "name": "page_10",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json"
        },
        {
            "name": "page_15",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json"
        }
    ]

    crop_count = 0
    for page in pages:
        print(f"Processing {page['name']}...")
        img = cv2.imread(str(page['image']))
        if img is None:
            print(f"Error: Could not read image {page['image']}")
            continue

        with open(page['gt'], 'r') as f:
            gt_data = json.load(f)

        for i, entry in enumerate(gt_data):
            box = entry['barline_location'] # [x1, y1, x2, y2]
            x1, y1, x2, y2 = box

            # Center of the barline
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            # Crop size
            # Barlines are tall, let's take a generous context
            # Target size 128x256 (W x H)
            w_half = 64
            h_half = 128

            # Clip coordinates
            cy1 = max(0, cy - h_half)
            cy2 = min(img.shape[0], cy + h_half)
            cx1 = max(0, cx - w_half)
            cx2 = min(img.shape[1], cx + w_half)

            crop = img[cy1:cy2, cx1:cx2]

            # Pad if at boundary
            if crop.shape[0] < h_half * 2 or crop.shape[1] < w_half * 2:
                pad_y1 = h_half - (cy - cy1)
                pad_y2 = h_half - (cy2 - cy)
                pad_x1 = w_half - (cx - cx1)
                pad_x2 = w_half - (cx2 - cx)
                crop = cv2.copyMakeBorder(crop, pad_y1, pad_y2, pad_x1, pad_x2, cv2.BORDER_CONSTANT, value=[255, 255, 255])

            save_path = output_dir / f"{page['name']}_tp_{i:04d}.png"
            cv2.imwrite(str(save_path), crop)
            crop_count += 1

    print(f"Extraction complete. Total TP crops: {crop_count}")

if __name__ == "__main__":
    extract_crops()
