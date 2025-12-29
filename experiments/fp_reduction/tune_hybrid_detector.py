
import json
import argparse
from pathlib import Path
import numpy as np
from typing import List, Tuple, Dict, Set

import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match, barline_iou, BarlineMatchResult

Box = Tuple[int, int, int, int]

def load_json_boxes(path: Path) -> List[Box]:
    with open(path, 'r') as f:
        data = json.load(f)
    
    boxes = []
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], list): # [[x1,y1,x2,y2], ...] (OMR-DLN)
            return [tuple(x) for x in data]
        elif isinstance(data[0], dict) and "barline_location" in data[0]: # GT
            return [tuple(item["barline_location"]) for item in data]
        else:
            print(f"Unknown list format in {path}")
            return []
    elif isinstance(data, dict):
        if "predictions" in data: # homr
            for pred in data["predictions"]:
                if "orig_bbox" in pred:
                    boxes.append(tuple(pred["orig_bbox"]))
                else:
                    print(f"Warning: prediction without orig_bbox in {path}")
        else:
            print(f"Unknown dict format in {path}")
            
    return boxes

def has_match(query_box: Box, references: List[Box], iou_thresh=0.5) -> bool:
    for ref in references:
        # Use robust barline_iou
        if barline_iou(query_box, ref) > iou_thresh:
            return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline detections JSON")
    parser.add_argument("--sr", type=Path, required=True, help="SR detections JSON")
    parser.add_argument("--omr", type=Path, required=True, help="OMR detections JSON")
    parser.add_argument("--gt", type=Path, required=True, help="GT detections JSON")
    args = parser.parse_args()

    baseline_boxes = load_json_boxes(args.baseline)
    sr_boxes = load_json_boxes(args.sr)
    omr_boxes = load_json_boxes(args.omr)
    gt_boxes = load_json_boxes(args.gt)

    print(f"Loaded {len(baseline_boxes)} Baseline predictions")
    print(f"Loaded {len(sr_boxes)} SR predictions")
    print(f"Loaded {len(omr_boxes)} OMR predictions")
    print(f"Loaded {len(gt_boxes)} GT boxes")

    # Analyze Baseline Candidates
    # Use greedy_barline_match to determine TPs against GT
    match_result = greedy_barline_match(baseline_boxes, gt_boxes)
    # Get TP indices (indices into baseline_boxes)
    tp_indices = set(m.pred_index for m in match_result.matches)
    
    print(f"Baseline TP (Project Logic): {len(tp_indices)}")
    print(f"Baseline FP (Project Logic): {len(baseline_boxes) - len(tp_indices)}")
    
    stats = {
        "TP_supported_neither": 0, "FP_supported_neither": 0,
        "TP_supported_SR_only": 0, "FP_supported_SR_only": 0,
        "TP_supported_OMR_only": 0, "FP_supported_OMR_only": 0,
        "TP_supported_both": 0, "FP_supported_both": 0
    }
    
    for i, b_box in enumerate(baseline_boxes):
        label = "TP" if i in tp_indices else "FP"
        
        # Support
        supp_sr = has_match(b_box, sr_boxes)
        supp_omr = has_match(b_box, omr_boxes)
        
        key = ""
        if supp_sr and supp_omr:
            key = f"{label}_supported_both"
        elif supp_sr:
            key = f"{label}_supported_SR_only"
        elif supp_omr:
            key = f"{label}_supported_OMR_only"
        else:
            key = f"{label}_supported_neither"
            
        stats[key] += 1
        
    print("\n--- Correlation Analysis ---")
    print(f"{'Category':<25} | {'TP':<5} | {'FP':<5} | {'Total':<5} | {'Precision':<10}")
    print("-" * 60)
    
    categories = ["both", "SR_only", "OMR_only", "neither"]
    total_tp = 0
    total_fp = 0
    
    for cat in categories:
        tp = stats[f"TP_supported_{cat}"]
        fp = stats[f"FP_supported_{cat}"]
        total = tp + fp
        prec = tp / total if total > 0 else 0
        print(f"Supported by {cat:<12} | {tp:<5} | {fp:<5} | {total:<5} | {prec:.2f}")
        total_tp += tp
        total_fp += fp
        
    print("-" * 60)
    print(f"{'Total':<25} | {total_tp:<5} | {total_fp:<5} | {total_tp+total_fp:<5}")

    # Conclusion simulation
    # Try rule: Keep if (SR or OMR)
    kept_tp = stats["TP_supported_both"] + stats["TP_supported_SR_only"] + stats["TP_supported_OMR_only"]
    kept_fp = stats["FP_supported_both"] + stats["FP_supported_SR_only"] + stats["FP_supported_OMR_only"]
    
    print(f"\nSimulation: Keep if (Supported by SR OR Supported by OMR)")
    print(f"Retained TP: {kept_tp} (Missed: {total_tp - kept_tp})")
    print(f"Retained FP: {kept_fp} (Removed: {total_fp - kept_fp})")

if __name__ == "__main__":
    main()
