
import argparse
import json
import os
import sys
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLOWorld

# Add src to path to import common modules
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
from common.barline_evaluation import greedy_barline_match, BarlineMatchResult

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate YOLO-World for Barline Detection")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--gt", type=str, required=True, help="Path to GT JSON")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save logs/results")
    parser.add_argument("--prompts", type=str, nargs="+", default=["barline"], help="Text prompts for Zero-Shot")
    parser.add_argument("--conf", type=float, default=0.1, help="Confidence threshold")
    parser.add_argument("--model-size", type=str, default="x", choices=["s", "m", "l", "x"], help="YOLOv8 World model size")
    return parser.parse_args()

def load_gt_boxes(gt_path):
    with open(gt_path, 'r') as f:
        data = json.load(f)
    # GT format is list of dicts with "barline_location"
    return [item["barline_location"] for item in data]

def main():
    args = parse_args()
    
    # Setup Output
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load Model
    model_path = Path(__file__).resolve() / "yolo_world" / "models"
    model_name = f"yolov8{args.model_size}-worldv2.pt"
    print(f"Loading {model_name}...")
    try:
        model = YOLOWorld(model_path /model_name)
    except Exception as e:
        print(f"Failed to load model from cache, trying download by usage: {e}")
        # Ultralytics will auto-download
        model = YOLOWorld(model_name)

    # Set Prompts
    print(f"Setting prompts: {args.prompts}")
    model.set_classes(args.prompts)
    
    # Inference
    print(f"Running inference on {args.image} with conf={args.conf}...")
    results = model.predict(args.image, conf=args.conf, save=False)
    result = results[0]
    
    # Parse Predictions
    pred_boxes = []
    
    # Visualize
    img_viz = cv2.imread(args.image)
    if img_viz is None: # Maybe path issues if not found
         print(f"Error reading image {args.image}")
         return

    for box in result.boxes:
        # xyxy format
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
        conf = float(box.conf[0].cpu().numpy())
        cls_id = int(box.cls[0].cpu().numpy())
        label = args.prompts[cls_id] if cls_id < len(args.prompts) else str(cls_id)
        
        pred_boxes.append((int(x1), int(y1), int(x2), int(y2)))
        
        # Draw on Viz
        cv2.rectangle(img_viz, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(img_viz, f"{label} {conf:.2f}", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

    viz_path = os.path.join(args.output_dir, "prediction_vis.jpg")
    cv2.imwrite(viz_path, img_viz)
    print(f"Saved visualization to {viz_path}")
    
    # Evaluation
    print("Loading Ground Truth...")
    gt_boxes = load_gt_boxes(args.gt)
    print(f"Loaded {len(gt_boxes)} GT boxes.")
    print(f"Loaded {len(pred_boxes)} Pred boxes.")
    
    # Match
    match_result = greedy_barline_match(pred_boxes, gt_boxes) # Using default thresholds
    
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    metrics = {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "Num_Preds": len(pred_boxes),
        "Num_GT": len(gt_boxes)
    }
    
    print("\nXXX RESULTS XXX")
    print(json.dumps(metrics, indent=2))
    
    metrics_path = os.path.join(args.output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    predictions_path = os.path.join(args.output_dir, "predictions.json")
    with open(predictions_path, "w") as f:
        json.dump(pred_boxes, f)

if __name__ == "__main__":
    main()
