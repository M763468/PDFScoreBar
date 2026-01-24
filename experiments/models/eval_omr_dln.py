
import argparse
import json
import os
import sys
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO

# Add root project dir to path to import common modules
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))
from src.common.barline_evaluation import greedy_barline_match, BarlineMatchResult
from src.common.preprocessing import apply_advanced_sr

# --- Configuration ---
# NOTE TO USER: Please download the pretrained model weights from the Google Drive link
# in the 'dmgonzalez8/OMR' repository. From the available models, download the 
# YOLOv8m model trained for MEASURE detection.
# Rename it to 'YOLOv8m_Measures.pt' and place it in the directory below.
MODEL_PATH = REPO_ROOT / "external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
BARLINE_WIDTH = 4 # px, width of inferred barline boxes for evaluation

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate OMR-DLN (YOLOv8 Measure Detection) for Barline Detection")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--gt", type=str, help="Path to GT JSON for barlines (optional)")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save logs/results")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold for measure detection")
    parser.add_argument("--enable-sr", action="store_true", help="Enable Super-Resolution (Real-ESRGAN x4)")
    parser.add_argument("--pre-computed-sr", type=str, help="Path to pre-computed SR image (skips SR inference)")
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
    try:
        print("--- DEBUG: OMR-DLN Script Start ---", file=sys.stderr)
        args = parse_args()
        
        os.makedirs(args.output_dir, exist_ok=True)
        
        # --- Model Loading ---
        print(f"--- DEBUG: Checking model path: {MODEL_PATH} ---", file=sys.stderr)
        if not Path(MODEL_PATH).exists():
            print(f"FATAL: Model not found at {MODEL_PATH}", file=sys.stderr)
            print("Please download the pretrained YOLOv8m measure detection model, rename it, and place it in the correct directory.", file=sys.stderr)
            sys.exit(1)
        
        print("--- DEBUG: Image loaded ---", file=sys.stderr)
        original_img_bgr = cv2.imread(args.image)
        if original_img_bgr is None:
            raise FileNotFoundError(f"Could not load image: {args.image}")
        
        # Use the loaded original image as the default inference input
        inference_input = original_img_bgr
        sr_scale = 1

        if args.pre_computed_sr:
             print(f"--- DEBUG: Loading pre-computed SR image: {args.pre_computed_sr} ---", file=sys.stderr)
             sr_img_bgr = cv2.imread(args.pre_computed_sr)
             if sr_img_bgr is None:
                 raise FileNotFoundError(f"Could not load pre-computed SR image: {args.pre_computed_sr}")
             
             original_h, original_w = original_img_bgr.shape[:2]
             up_h, up_w = sr_img_bgr.shape[:2]
             
             # Calculate scale
             inferred_scale = round(up_w / original_w) if original_w else 1
             if inferred_scale >= 2:
                 sr_scale = inferred_scale
                 inference_input = sr_img_bgr
                 print(f"--- DEBUG: Using pre-computed SR image (scale x{sr_scale}) ---", file=sys.stderr)
             else:
                 print(f"--- WARN: Pre-computed SR image resolution is not significantly higher. Treating as 1x. ---", file=sys.stderr)
                 inference_input = sr_img_bgr # Still use it, but scale is 1
                 
        elif args.enable_sr:
            requested_sr_scale = 4
            original_h, original_w = original_img_bgr.shape[:2]
            print(f"--- DEBUG: Applying SR (x{requested_sr_scale})... ---", file=sys.stderr)
            # Use original_img_bgr as source
            sr_img_bgr = apply_advanced_sr(original_img_bgr, model_name="RealESRGAN_x4plus", scale=requested_sr_scale)
            
            up_h, up_w = sr_img_bgr.shape[:2]
            inferred_scale = round(up_w / original_w) if original_w else 1
            if inferred_scale >= 2 and up_w >= original_w * 2 and up_h >= original_h * 2:
                sr_scale = inferred_scale
                inference_input = sr_img_bgr
            else:
                print(
                    f"--- WARN: SR output resolution did not increase "
                    f"({original_w}x{original_h} -> {up_w}x{up_h}); treating as no-SR. ---",
                    file=sys.stderr,
                )
                inference_input = original_img_bgr # Fallback to original
            
            print(f"--- DEBUG: SR applied (effective scale x{sr_scale}) ---", file=sys.stderr)
        
        # Determine img_bgr for visualization (use inference input)
        img_bgr = inference_input

        print(f"--- DEBUG: Loading model: {MODEL_PATH} ---", file=sys.stderr)
        model = YOLO(MODEL_PATH)
        print("--- DEBUG: Model loaded successfully ---", file=sys.stderr)
    
        # --- Inference ---
        print(f"--- DEBUG: Running prediction with conf={args.conf} ---", file=sys.stderr)
        results = model.predict(inference_input, conf=args.conf, save=False)
        result = results[0]
        print("--- DEBUG: Prediction finished ---", file=sys.stderr)
        
        # --- Process Detections ---
        img_viz = img_bgr.copy()
        
        measure_boxes = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            
            mx1, my1, mx2, my2 = int(x1), int(y1), int(x2), int(y2)
            measure_boxes.append((mx1, my1, mx2, my2))
            
            cv2.rectangle(img_viz, (mx1, my1), (mx2, my2), (0, 255, 0), 2)
            cv2.putText(img_viz, f"measure {conf:.2f}", (mx1, my1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        pred_barlines_inference = infer_barlines_from_measures(measure_boxes)
        
        pred_barlines_1x = []
        for (x1, y1, x2, y2) in pred_barlines_inference:
            pred_barlines_1x.append(
                (int(x1/sr_scale), int(y1/sr_scale), int(x2/sr_scale), int(y2/sr_scale))
            )
            cv2.rectangle(img_viz, (x1, y1), (x2, y2), (255, 0, 0), 1)

        viz_path = os.path.join(args.output_dir, "prediction_vis.jpg")
        cv2.imwrite(viz_path, img_viz)
        print(f"Saved visualization to {viz_path}")
        
        # --- Evaluation ---
        if args.gt:
            print("Loading Ground Truth barlines...")
            gt_boxes = load_gt_boxes(args.gt)
            
            print(f"Loaded {len(gt_boxes)} GT boxes.")
            print(f"Detected {len(measure_boxes)} measures, inferring {len(pred_barlines_1x)} barlines (1x scaled).")
            
            match_result = greedy_barline_match(pred_barlines_1x, gt_boxes)
            
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
                "Num_Barline_Preds": len(pred_barlines_1x),
                "Num_GT": len(gt_boxes)
            }
            
            print("\n--- OMR-DLN Evaluation Results ---")
            print(json.dumps(metrics, indent=2))
            
            metrics_path = os.path.join(args.output_dir, "metrics.json")
            with open(metrics_path, "w") as f:
                json.dump(metrics, f, indent=2)
        else:
            print("\n--- OMR-DLN Inference ---")
            print(f"Detected {len(measure_boxes)} measures, inferred {len(pred_barlines_1x)} barlines.")
            print("No Ground Truth provided, skipping metrics calculation.")

        predictions_path = os.path.join(args.output_dir, "predictions.json")
        with open(predictions_path, "w") as f:
            json.dump(pred_barlines_1x, f)
        
        print("--- DEBUG: Script End ---", file=sys.stderr)

    except Exception as e:
        # Catch ANY exception and write to a file
        with open("/workspace/logs/omr_dln_error.log", "w") as f:
            f.write(f"An exception occurred: {type(e).__name__}\n")
            f.write(str(e) + "\n")
            import traceback
            f.write(traceback.format_exc())


if __name__ == "__main__":
    main()
