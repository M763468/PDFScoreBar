import argparse
import json
import os
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

# Add root project dir to path to import common modules
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))
from src.common.preprocessing import apply_advanced_sr

# --- Configuration ---
# NOTE TO USER: Please download the pretrained model weights from the Google Drive link
# in the 'dmgonzalez8/OMR' repository. From the available models, download the
# YOLOv8m model trained for MEASURE detection.
# Rename it to 'YOLOv8m_Measures.pt' and place it in the directory below.
MODEL_PATH = REPO_ROOT / "external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
BARLINE_WIDTH = 4  # px, width of inferred barline boxes for evaluation


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate OMR-DLN (YOLOv8 Measure Detection) for Barline Detection"
    )
    parser.add_argument("--images", nargs="+", help="List of input images")
    parser.add_argument("--image", type=str, help="Path to input image (legacy)")
    parser.add_argument("--gt", type=str, help="Path to GT JSON for barlines (optional)")
    parser.add_argument(
        "--output-dir", type=str, required=True, help="Directory to save logs/results"
    )
    parser.add_argument(
        "--conf", type=float, default=0.25, help="Confidence threshold for measure detection"
    )
    parser.add_argument(
        "--enable-sr", action="store_true", help="Enable Super-Resolution (Real-ESRGAN x4)"
    )
    parser.add_argument(
        "--pre-computed-sr",
        type=str,
        help="Path to pre-computed SR image or directory containing SR images.",
    )
    return parser.parse_args()


def load_gt_boxes(gt_path):
    """Loads ground truth barlines."""
    with open(gt_path, "r") as f:
        data = json.load(f)
    return [item["barline_location"] for item in data]


def infer_barlines_from_measures(measure_boxes):
    """
    Converts measure bounding boxes into barline bounding boxes.
    A measure (x1, y1, x2, y2) implies a left barline and a right barline,
    using the measure's own vertical span.
    """
    barlines = []
    for mx1, my1, mx2, my2 in measure_boxes:
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

        # Collect images
        image_paths = []
        if args.images:
            image_paths.extend(args.images)
        if args.image:
            image_paths.append(args.image)

        if not image_paths:
            print("Error: No images provided via --images or --image", file=sys.stderr)
            sys.exit(1)

        # --- Model Loading ---
        print(f"--- DEBUG: Checking model path: {MODEL_PATH} ---", file=sys.stderr)
        if not Path(MODEL_PATH).exists():
            print(f"FATAL: Model not found at {MODEL_PATH}", file=sys.stderr)
            print(
                "Please download the pretrained YOLOv8m measure detection model, rename it, and place it in the correct directory.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"--- DEBUG: Loading model: {MODEL_PATH} ---", file=sys.stderr)
        model = YOLO(MODEL_PATH)
        print("--- DEBUG: Model loaded successfully ---", file=sys.stderr)

        # Pre-computed SR handling (Single file scenario primarily, but check if we can support batch mapping later)
        # For now, if --pre-computed-sr is provided, it assumes specific file.
        # TODO: If batching, pre-computed SR needs to be a mapping or directory.
        # Current batch implementation assumes standard SR or no SR for simplicity in batch.

        if args.pre_computed_sr and len(image_paths) > 1:
            print(
                "Warning: --pre-computed-sr provided with multiple images. This might not map correctly unless logic handles it. Ignoring or using as is.",
                file=sys.stderr,
            )
            # For this Phase 2, we assume batch mode relies on internal SR or standard input.

        # Determine Batch SR requested
        requested_sr_scale = 1
        if args.enable_sr:
            requested_sr_scale = 4

        for img_path_str in image_paths:
            img_path = Path(img_path_str)
            stem = img_path.stem
            print(f"--- Processing {stem} ---", file=sys.stderr)

            # Prepare Page Output Dir
            # Structure: output_dir / stem / ... or just output_dir?
            # Original script saved to output_dir root. If multiple images, we must subfolder or name distinctively.
            # homr_evaluator uses output_root / stem / ...
            # Let's use a subfolder per image to avoid collisions.
            page_output_dir = Path(args.output_dir) / stem
            page_output_dir.mkdir(parents=True, exist_ok=True)

            original_img_bgr = cv2.imread(str(img_path))
            if original_img_bgr is None:
                print(f"Error: Could not load image {img_path}. Skipping.", file=sys.stderr)
                continue

            inference_input = original_img_bgr
            sr_scale = 1

            # SR Logic (Per Image)
            if args.pre_computed_sr:
                sr_base = Path(args.pre_computed_sr)
                sr_img_path = None

                # 1. Try directory match patterns (higher priority for batch runs)
                # homr_evaluator style: pre_computed_sr / stem / stem / stem.png
                p1 = sr_base / stem / stem / f"{stem}.png"
                # homr_evaluator style alternative: pre_computed_sr / stem / f"{stem}.png"
                p1b = sr_base / stem / f"{stem}.png"
                # Simple style: pre_computed_sr / stem.png
                p2 = sr_base / f"{stem}.png"

                if p1.exists():
                    sr_img_path = p1
                elif p1b.exists():
                    sr_img_path = p1b
                elif p2.exists():
                    sr_img_path = p2
                elif sr_base.is_file():
                    # 3. Fallback to explicit file (legacy/explicit)
                    sr_img_path = sr_base

                if sr_img_path and sr_img_path.exists():
                    print(f"Using pre-computed SR: {sr_img_path}", file=sys.stderr)
                    sr_img_bgr = cv2.imread(str(sr_img_path))
                    if sr_img_bgr is not None:
                        original_h, original_w = original_img_bgr.shape[:2]
                        up_h, up_w = sr_img_bgr.shape[:2]
                        inferred_scale = round(up_w / original_w) if original_w else 1
                        if inferred_scale >= 2:
                            sr_scale = inferred_scale
                            inference_input = sr_img_bgr
                else:
                    if len(image_paths) == 1:
                        print(
                            f"Warning: --pre-computed-sr provided but not found for {stem}.",
                            file=sys.stderr,
                        )

            elif args.enable_sr:
                print(f"--- Applying SR (x{requested_sr_scale}) for {stem}... ---", file=sys.stderr)
                try:
                    sr_img_bgr = apply_advanced_sr(
                        original_img_bgr, model_name="RealESRGAN_x4plus", scale=requested_sr_scale
                    )
                    up_h, up_w = sr_img_bgr.shape[:2]
                    original_h, original_w = original_img_bgr.shape[:2]
                    inferred_scale = round(up_w / original_w) if original_w else 1
                    if inferred_scale >= 2 and up_w >= original_w * 2:
                        sr_scale = inferred_scale
                        inference_input = sr_img_bgr
                except Exception as e:
                    print(f"SR Failed for {stem}: {e}. using original.", file=sys.stderr)

            # --- Inference ---
            results = model.predict(inference_input, conf=args.conf, save=False, verbose=False)
            result = results[0]

            # --- Process Detections ---
            img_viz = inference_input.copy()

            measure_boxes = []
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                # conf = float(box.conf[0].cpu().numpy())
                mx1, my1, mx2, my2 = int(x1), int(y1), int(x2), int(y2)
                measure_boxes.append((mx1, my1, mx2, my2))
                cv2.rectangle(img_viz, (mx1, my1), (mx2, my2), (0, 255, 0), 2)

            pred_barlines_inference = infer_barlines_from_measures(measure_boxes)

            pred_barlines_1x = []
            for x1, y1, x2, y2 in pred_barlines_inference:
                pred_barlines_1x.append(
                    (int(x1 / sr_scale), int(y1 / sr_scale), int(x2 / sr_scale), int(y2 / sr_scale))
                )
                cv2.rectangle(img_viz, (x1, y1), (x2, y2), (255, 0, 0), 1)

            viz_path = page_output_dir / "prediction_vis.jpg"
            cv2.imwrite(str(viz_path), img_viz)

            # --- Save Results ---
            # Save as predictions.json
            predictions_path = page_output_dir / "predictions.json"
            with open(predictions_path, "w") as f:
                json.dump(pred_barlines_1x, f)

            # --- Evaluation (Optional) ---
            # GT support in batch is tricky unless map is provided.
            # Only support if len=1 for now or if we parse --gt map.
            # Original supported --gt as single file.
            pass

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
