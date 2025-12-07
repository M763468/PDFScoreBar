
import argparse
import json
import os
import sys
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO

# Add root project dir to path to import common modules
sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.common.barline_evaluation import greedy_barline_match, BarlineMatchResult

# --- Configuration ---
# NOTE TO USER: Please download the pretrained model weights from the Google Drive link
# in the 'dmgonzalez8/OMR' repository. From the available models, download the 
# YOLOv8m model trained for MEASURE detection.
# Rename it to 'YOLOv8m_Measures.pt' and place it in the directory below.
MODEL_PATH = "external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
BARLINE_WIDTH = 4 # px, width of inferred barline boxes for evaluation

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate OMR-DLN (YOLOv8 Measure Detection) for Barline Detection")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--gt", type=str, required=True, help="Path to GT JSON for barlines")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save logs/results")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold for measure detection")
    return parser.parse_args()

def load_gt_boxes(gt_path):
    """Loads ground truth barlines."""
    with open(gt_path, 'r') as f:
        data = json.load(f)
    return [item["barline_location"] for item in data]

def infer_barlines_from_measures(measure_boxes):
    """
    Converts measure bounding boxes into barline bounding boxes.
    A measure (x1, y1, x2, y2) implies a left barline and a right barline,
    using the measure's own vertical span.
    """
    barlines = []
    for (mx1, my1, mx2, my2) in measure_boxes:
        # Infer left barline from the left edge, using the measure's y-span
        barlines.append((mx1 - BARLINE_WIDTH // 2, my1, mx1 + BARLINE_WIDTH // 2, my2))
        # Infer right barline from the right edge, using the measure's y-span
        barlines.append((mx2 - BARLINE_WIDTH // 2, my1, mx2 + BARLINE_WIDTH // 2, my2))
    return barlines

def main():
    args = parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # --- Model Loading ---
    if not Path(MODEL_PATH).exists():
        print(f"FATAL: Model not found at {MODEL_PATH}")
        print("Please download the pretrained YOLOv8m measure detection model, rename it, and place it in the correct directory.")
        sys.exit(1)
    
    print(f"Loading model: {MODEL_PATH}...")
    model = YOLO(MODEL_PATH)
    
    # --- Inference ---
    print(f"Running measure detection on {args.image} with conf={args.conf}...")
    results = model.predict(args.image, conf=args.conf, save=False)
    result = results[0]
    
    # --- Process Detections ---
    img_viz = cv2.imread(args.image)
    h, w, _ = img_viz.shape
    
    measure_boxes = []
    for box in result.boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        conf = float(box.conf[0].cpu().numpy())
        
        # Cast to int for processing and serialization
        measure_boxes.append((int(x1), int(y1), int(x2), int(y2)))
        
        # Draw detected MEASURE box on viz image
        cv2.rectangle(img_viz, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2) # Green for measures
        cv2.putText(img_viz, f"measure {conf:.2f}", (int(x1), int(y1) - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # --- Infer Barlines ---
    pred_barlines = infer_barlines_from_measures(measure_boxes)
    
    # Draw INFERRED barlines on viz image
    for (x1, y1, x2, y2) in pred_barlines:
        # Use a different color to distinguish inferred barlines
        cv2.rectangle(img_viz, (x1, y1), (x2, y2), (255, 0, 0), 1) # Blue for barlines
        
    viz_path = os.path.join(args.output_dir, "prediction_vis.jpg")
    cv2.imwrite(viz_path, img_viz)
    print(f"Saved visualization to {viz_path}")
    
    # --- Evaluation ---
    print("Loading Ground Truth barlines...")
    gt_boxes = load_gt_boxes(args.gt)
    print(f"Loaded {len(gt_boxes)} GT boxes.")
    print(f"Detected {len(measure_boxes)} measures, inferring {len(pred_barlines)} barlines.")
    
    match_result = greedy_barline_match(pred_barlines, gt_boxes)
    
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    metrics = {
        "TP": tp, "FP": fp, "FN": fn,
        "Precision": precision, "Recall": recall, "F1": f1,
        "Num_Measure_Preds": len(measure_boxes),
        "Num_Barline_Preds": len(pred_barlines),
        "Num_GT": len(gt_boxes)
    }
    
    print("\n--- OMR-DLN Evaluation Results ---")
    print(json.dumps(metrics, indent=2))
    
    # Save artifacts
    metrics_path = os.path.join(args.output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    predictions_path = os.path.join(args.output_dir, "predictions.json")
    with open(predictions_path, "w") as f:
        json.dump(pred_barlines, f)

if __name__ == "__main__":
    main()
