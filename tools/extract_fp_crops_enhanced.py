#!/usr/bin/env python3
import json
import cv2
import os
from pathlib import Path
import numpy as np

def barline_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    
    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0
    
    inter_area = (inter_x2 - inter_x1 + 1) * (inter_y2 - inter_y1 + 1)
    area1 = (x2_1 - x1_1 + 1) * (y2_1 - y1_1 + 1)
    area2 = (x2_2 - x1_2 + 1) * (y2_2 - y1_2 + 1)
    
    return inter_area / float(area1 + area2 - inter_area)

def extract_fp_crops():
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / "logs/fp_crops_enhanced"
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = [
        {
            "name": "page_001",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
            "preds": repo_root / "logs/phase5b_confirmed_union_eval/page_001_hybrid_preds.json"
        },
        {
            "name": "page_3",
            "image": repo_root / "logs/homr_eval/baseline_for_hybrid/page_3/page_3.png",
            "gt": repo_root / "data/evaluation/annotations/page_003/boxes_sorted.json",
            "preds": repo_root / "logs/phase5b_confirmed_union_eval/page_3_hybrid_preds.json"
        },
        {
            "name": "page_004",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
            "preds": repo_root / "logs/phase5b_confirmed_union_eval/page_004_hybrid_preds.json"
        },
        {
            "name": "page_10",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json",
            "preds": repo_root / "logs/phase5b_confirmed_union_eval/page_10_hybrid_preds.json"
        },
        {
            "name": "page_15",
            "image": repo_root / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15.png",
            "gt": repo_root / "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json",
            "preds": repo_root / "logs/phase5b_confirmed_union_eval/page_15_hybrid_preds.json"
        }
    ]

    total_fp_count = 0
    for page in pages:
        print(f"Processing {page['name']}...")
        img = cv2.imread(str(page['image']))
        if img is None:
            print(f"Error: Could not read image {page['image']}")
            continue
        
        with open(page['gt'], 'r') as f:
            gt_data = json.load(f)
            gt_boxes = [entry['barline_location'] for entry in gt_data]
        
        with open(page['preds'], 'r') as f:
            pred_boxes = json.load(f)
            
        # Match preds to GT to find FPs
        matched_indices = set()
        for gt_box in gt_boxes:
            best_iou = 0
            best_idx = -1
            for i, pred_box in enumerate(pred_boxes):
                iou = barline_iou(gt_box, pred_box)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            if best_iou > 0.5:
                matched_indices.add(best_idx)
        
        fp_indices = [i for i in range(len(pred_boxes)) if i not in matched_indices]
        print(f"  Found {len(fp_indices)} FPs out of {len(pred_boxes)} candidates.")
        
        page_fp_count = 0
        for idx in fp_indices:
            box = pred_boxes[idx]
            x1, y1, x2, y2 = box
            
            # Center of the candidate
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            
            # Crop size (same as TP)
            w_half = 64
            h_half = 128
            
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

            save_path = output_dir / f"{page['name']}_fp_{idx:04d}.png"
            cv2.imwrite(str(save_path), crop)
            page_fp_count += 1
            
        total_fp_count += page_fp_count
            
    print(f"Extraction complete. Total FP crops: {total_fp_count}")

if __name__ == "__main__":
    extract_fp_crops()
