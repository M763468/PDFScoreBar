
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import torch

# Add GroundingDINO to path
grounding_dino_path = Path(__file__).resolve().parents[1] / "grounding_dino"
sys.path.append(str(grounding_dino_path))

# Add src to path to import common modules
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
from common.barline_evaluation import greedy_barline_match

# Grounding DINO imports
from groundingdino.util.inference import load_model, load_image, predict, annotate

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate GroundingDINO for Barline Detection")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--gt", type=str, required=True, help="Path to GT JSON")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save logs/results")
    parser.add_argument("--prompt", type=str, default="barline", help="Text prompt for detection")
    parser.add_argument("--box-threshold", type=float, default=0.35, help="Box threshold")
    parser.add_argument("--text-threshold", type=float, default=0.25, help="Text threshold")
    
    # Get config and weights from the submodule directory structure
    repo_root = Path(__file__).resolve().parents[2]
    default_config = str(repo_root / "external/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py")
    default_weights = str(repo_root / "external/grounding_dino/weights/groundingdino_swint_ogc.pth")
    
    parser.add_argument("--config", type=str, default=default_config, help="Path to GroundingDINO config file")
    parser.add_argument("--weights", type=str, default=default_weights, help="Path to GroundingDINO weights file")
    parser.add_argument("--cpu-only", action="store_true", help="Run on CPU only")
    
    return parser.parse_args()

def load_gt_boxes(gt_path):
    with open(gt_path, 'r') as f:
        data = json.load(f)
    return [item["barline_location"] for item in data]

def main():
    args = parse_args()
    
    # Setup Output
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load Model
    print("Loading GroundingDINO model...")
    device = "cuda" if torch.cuda.is_available() and not args.cpu_only else "cpu"
    print(f"Using device: {device}")
    model = load_model(args.config, args.weights, device=device)
    
    # Load Image
    print(f"Loading image: {args.image}")
    image_source, image = load_image(args.image) # image is a tensor

    # Inference
    print(f"Running inference with prompt: '{args.prompt}'")
    boxes, logits, phrases = predict(
        model=model,
        image=image,
        caption=args.prompt,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        device=device,
    )
    
    # Parse Predictions and Visualize
    pred_boxes = []
    # GroundingDINO returns boxes in (cx, cy, w, h) normalized format, convert to (x1, y1, x2, y2) absolute
    h, w, _ = image_source.shape
    boxes_abs = boxes * torch.Tensor([w, h, w, h])
    boxes_xyxy = boxes_abs.cpu().numpy()

    for box in boxes_xyxy:
        cx, cy, wb, hb = box
        x1 = int(cx - wb / 2)
        y1 = int(cy - hb / 2)
        x2 = int(cx + wb / 2)
        y2 = int(cy + hb / 2)
        pred_boxes.append((x1, y1, x2, y2))
        
    print(f"Detected {len(pred_boxes)} boxes.")

    # Save annotated image
    annotated_frame = annotate(image_source=image_source, boxes=boxes, logits=logits, phrases=phrases)
    viz_path = os.path.join(args.output_dir, "prediction_vis.jpg")
    cv2.imwrite(viz_path, annotated_frame)
    print(f"Saved visualization to {viz_path}")

    # Evaluation
    print("Loading Ground Truth...")
    gt_boxes = load_gt_boxes(args.gt)
    print(f"Loaded {len(gt_boxes)} GT boxes.")
    
    # Match
    match_result = greedy_barline_match(pred_boxes, gt_boxes)
    
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
        "Num_GT": len(gt_boxes),
        "params": {
            "prompt": args.prompt,
            "box_threshold": args.box_threshold,
            "text_threshold": args.text_threshold,
        }
    }
    
    print("\n--- RESULTS ---")
    print(json.dumps(metrics, indent=2))
    
    # Save results
    metrics_path = os.path.join(args.output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    predictions_path = os.path.join(args.output_dir, "predictions.json")
    with open(predictions_path, "w") as f:
        json.dump(pred_boxes, f, indent=2)

if __name__ == "__main__":
    main()
