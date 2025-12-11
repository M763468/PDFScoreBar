import argparse
import json
import os
import sys
from pathlib import Path

# Add root project dir to path to import common modules
sys.path.append(str(Path(__file__).resolve().parents[3])) # Adjust path to reach project root

from src.common.barline_evaluation import greedy_barline_match, BarlineMatchResult

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Hybrid Barline Detector (homr + OMR-DLN filter)")
    parser.add_argument("--homr-predictions", type=str, required=True, help="Path to homr detections JSON")
    parser.add_argument("--omr-dln-predictions", type=str, required=True, help="Path to OMR-DLN detections JSON")
    parser.add_argument("--gt", type=str, required=True, help="Path to Ground Truth JSON for barlines")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save logs/results")
    parser.add_argument("--iou-threshold", type=float, default=0.5, help="IoU threshold for filtering and evaluation")
    return parser.parse_args()

def load_predictions(file_path, type="homr"):
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    if type == "homr":
        # homr detections have {'predictions': [{'orig_bbox': [x1, y1, x2, y2]}, ...]}
        return [p['orig_bbox'] for p in data['predictions']]
    elif type == "omr_dln":
        # OMR-DLN detections are directly a list of [x1, y1, x2, y2]
        return data
    else:
        raise ValueError("Unknown prediction type")

def load_gt_boxes(gt_path):
    """Loads ground truth barlines."""
    with open(gt_path, 'r') as f:
        data = json.load(f)
    return [item["barline_location"] for item in data]

def calculate_iou(box1, box2):
    # box format: [x1, y1, x2, y2]
    x1_inter = max(box1[0], box2[0])
    y1_inter = max(box1[1], box2[1])
    x2_inter = min(box1[2], box2[2])
    y2_inter = min(box1[3], box2[3])

    inter_area = max(0, x2_inter - x1_inter) * max(0, y2_inter - y1_inter)

    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    union_area = box1_area + box2_area - inter_area
    if union_area == 0:
        return 0.0
    return inter_area / union_area

def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    # Load predictions
    homr_preds = load_predictions(args.homr_predictions, type="homr")
    omr_dln_preds = load_predictions(args.omr_dln_predictions, type="omr_dln")
    
    # Hybrid Filtering Logic
    filtered_predictions = []
    for homr_box in homr_preds:
        is_supported_by_omr_dln = False
        for omr_dln_box in omr_dln_preds:
            if calculate_iou(homr_box, omr_dln_box) >= args.iou_threshold:
                is_supported_by_omr_dln = True
                break
        if is_supported_by_omr_dln:
            filtered_predictions.append(homr_box)

    # Load Ground Truth
    gt_boxes = load_gt_boxes(args.gt)

    # Evaluate
    match_result = greedy_barline_match(filtered_predictions, gt_boxes, iou_threshold=args.iou_threshold)

    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    metrics = {
        "TP": tp, "FP": fp, "FN": fn,
        "Precision": precision, "Recall": recall, "F1": f1,
        "Num_homr_preds": len(homr_preds),
        "Num_omr_dln_preds": len(omr_dln_preds),
        "Num_filtered_preds": len(filtered_predictions),
        "Num_GT": len(gt_boxes)
    }

    print("\n--- Hybrid Detector Evaluation Results ---")
    print(json.dumps(metrics, indent=2))

    # Save results
    metrics_path = os.path.join(args.output_dir, "hybrid_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    predictions_path = os.path.join(args.output_dir, "hybrid_predictions.json")
    with open(predictions_path, "w") as f:
        json.dump(filtered_predictions, f)

if __name__ == "__main__":
    main()
