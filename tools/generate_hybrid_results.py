
import json
import argparse
import sys
from pathlib import Path

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match, barline_iou, BarlineMatchResult

def load_json_boxes(path: Path):
    with open(path, 'r') as f:
        data = json.load(f)
    if isinstance(data, list):
        if not data: return []
        if isinstance(data[0], list): return [tuple(x) for x in data]
        if isinstance(data[0], dict) and "barline_location" in data[0]: return [tuple(item["barline_location"]) for item in data]
    elif isinstance(data, dict):
        if "predictions" in data:
            boxes = []
            for pred in data["predictions"]:
                if "orig_bbox" in pred: boxes.append(tuple(pred["orig_bbox"]))
            return boxes
    return []

def has_match(query_box, references, iou_thresh=0.5):
    for ref in references:
        if barline_iou(query_box, ref) > iou_thresh:
            return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sr", type=Path, required=True)
    parser.add_argument("--omr", type=Path, required=True)
    parser.add_argument("--gt", type=Path, help="Path to Ground Truth JSON (optional)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline_boxes = load_json_boxes(args.baseline)
    sr_boxes = load_json_boxes(args.sr)
    omr_boxes = load_json_boxes(args.omr)
    
    gt_boxes = []
    if args.gt:
        gt_boxes = load_json_boxes(args.gt)
        print(f"Loaded {len(baseline_boxes)} Baseline, {len(sr_boxes)} SR, {len(omr_boxes)} OMR, {len(gt_boxes)} GT.")
    else:
        print(f"Loaded {len(baseline_boxes)} Baseline, {len(sr_boxes)} SR, {len(omr_boxes)} OMR. (No GT provided)")

    # Apply Hybrid Rule: Keep Baseline if supported by SR or OMR
    hybrid_preds = []
    for box in baseline_boxes:
        if has_match(box, sr_boxes) or has_match(box, omr_boxes):
            hybrid_preds.append(box)
            
    print(f"Hybrid Predictions: {len(hybrid_preds)}")

    # Compute Final Metrics only if GT is present
    if args.gt:
        match_result = greedy_barline_match(hybrid_preds, gt_boxes)
        
        tp = len(match_result.matches)
        fp = len(match_result.false_positive_indices)
        fn = len(match_result.false_negative_indices)
        soft = len(match_result.soft_matches)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        print("\n--- Final Hybrid Metrics ---")
        print(f"TP: {tp}")
        print(f"FP: {fp}")
        print(f"FN: {fn}")
        print(f"Soft Matches: {soft}")
        print(f"Precision: {precision:.4f}")
        print(f"Recall: {recall:.4f}")
        print(f"F1: {f1:.4f}")
    
    # Save Results
    with open(args.output, 'w') as f:
        json.dump(hybrid_preds, f, indent=2)
    print(f"Saved hybrid predictions to {args.output}")

if __name__ == "__main__":
    main()
