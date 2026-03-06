import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from common.barline_evaluation import greedy_barline_match
from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", type=str, required=True)
    parser.add_argument("--gt", type=str, required=True)
    parser.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.pred) as f:
        data = json.load(f)

    preds = [tuple(p["orig_bbox"]) for p in data.get("predictions", [])]
    gt_boxes = load_ground_truth_boxes(Path(args.gt))

    match_result = greedy_barline_match(preds, gt_boxes, iou_threshold=args.iou)

    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"Metrics for {args.pred}:")
    print(f"  P: {precision:.4f}")
    print(f"  R: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    print(f"  TP: {tp}, FP: {fp}, FN: {fn}")


if __name__ == "__main__":
    main()
