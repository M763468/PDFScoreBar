
import json
import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.common.barline_evaluation import greedy_barline_match
from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", type=str, required=True)
    parser.add_argument("--gt", type=str, required=True)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--rule", type=str, default="center_anchor")
    args = parser.parse_args()

    with open(args.pred) as f:
        data = json.load(f)
    
    # Handle both complex dict format and simple list of lists
    if isinstance(data, dict):
        preds = [tuple(p["orig_bbox"]) for p in data.get("predictions", [])]
    else:
        preds = [tuple(b) for b in data]

    gt_boxes = load_ground_truth_boxes(Path(args.gt))
    
    match_result = greedy_barline_match(
        preds, gt_boxes, 
        rule_name=args.rule,
        iou_threshold=args.iou,
        vov_threshold=0.5,
        xdist_threshold=12.0
    )
    
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"Metrics for {args.pred} (Rule: {args.rule}):")
    print(f"  P: {precision:.4f}")
    print(f"  R: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    print(f"  TP: {tp}, FP: {fp}, FN: {fn}")

if __name__ == "__main__":
    main()
