
import argparse
import json
import cv2
import sys
from pathlib import Path
from typing import Optional

# Add project root to path to allow imports from src
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score, Page

def render_overlay(score: Score, image_path: Path, output_path: Path):
    """Generates a visualization overlay for the processed score."""
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Error: Could not read image for overlay: {image_path}")
        return

    overlay = img.copy()
    
    # 1. Draw Staves (Blue boxes) - Transparent
    overlay_temp = overlay.copy()
    for page in score.pages:
        for sys_obj in page.systems:
            for staff in sys_obj.staves:
                cv2.rectangle(overlay_temp, 
                              (staff.bbox.x1, staff.bbox.y1), 
                              (staff.bbox.x2, staff.bbox.y2), 
                              (255, 0, 0), -1) # Blue fill
    cv2.addWeighted(overlay_temp, 0.15, overlay, 0.85, 0, overlay)
    
    # 2. Draw Barlines and Measures
    for page in score.pages:
        for sys_obj in page.systems:
            # Draw Measures (Numbers and boundaries)
            top_staff = min(sys_obj.staves, key=lambda s: s.bbox.y1)
            text_y = top_staff.bbox.y1 - 10
            
            for measure in sys_obj.measures:
                # Center number in measure
                center_x = int((measure.bbox.x1 + measure.bbox.x2) / 2)
                text = str(measure.number)
                font_scale = 1.2
                thickness = 2
                (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                
                cv2.putText(overlay, text, (center_x - text_w // 2, text_y), 
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 150, 0), thickness, cv2.LINE_AA)
                
                # Draw faint green boundaries
                cv2.line(overlay, (measure.bbox.x1, text_y), (measure.bbox.x1, text_y + 10), (0, 255, 0), 1)
                cv2.line(overlay, (measure.bbox.x2, text_y), (measure.bbox.x2, text_y + 10), (0, 255, 0), 1)

            # Draw all barlines belonging to staves
            for staff in sys_obj.staves:
                for bar in staff.barlines:
                    color = (0, 0, 255) # Red
                    if getattr(bar, 'is_ghost', False):
                        color = (255, 0, 255) # Magenta for ghost
                    cv2.rectangle(overlay, (bar.bbox.x1, bar.bbox.y1), (bar.bbox.x2, bar.bbox.y2), color, 2)

    cv2.imwrite(str(output_path), overlay)
    print(f"Overlay saved to: {output_path}")

def score_to_dict(score: Score) -> dict:
    """Converts the Score object tree into a serializable dictionary."""
    data = {"pages": []}
    for p in score.pages:
        page_data = {
            "page_number": p.page_number,
            "width": p.width,
            "height": p.height,
            "systems": []
        }
        for s in p.systems:
            sys_data = {
                "staves": [{"bbox": [st.bbox.x1, st.bbox.y1, st.bbox.x2, st.bbox.y2]} for st in s.staves],
                "measures": []
            }
            for m in s.measures:
                m_data = {
                    "number": m.number,
                    "bbox": [m.bbox.x1, m.bbox.y1, m.bbox.x2, m.bbox.y2]
                }
                sys_data["measures"].append(m_data)
            page_data["systems"].append(sys_data)
        data["pages"].append(page_data)
    return data

def normalize_barlines(raw_data):
    """Normalizes various barline JSON formats into a list of [x1, y1, x2, y2]."""
    if not raw_data:
        return []
    
    normalized = []
    for item in raw_data:
        if isinstance(item, list) and len(item) == 4:
            normalized.append(item)
        elif isinstance(item, dict):
            # Try GT format: {"barline_location": [x1, y1, x2, y2]}
            if "barline_location" in item:
                normalized.append(item["barline_location"])
            # Try flat dict: {"x1": ..., "y1": ...}
            elif all(k in item for k in ["x1", "y1", "x2", "y2"]):
                normalized.append([item["x1"], item["y1"], item["x2"], item["y2"]])
    return normalized

def main():
    parser = argparse.ArgumentParser(description="Add measure numbers to detected barlines.")
    parser.add_argument("--barlines", type=Path, required=True, help="Path to detected barlines JSON")
    parser.add_argument("--staff-mask", type=Path, required=True, help="Path to homr staff mask PNG")
    parser.add_argument("--image", type=Path, required=True, help="Path to original score image (for scale reference)")
    parser.add_argument("--output-json", type=Path, help="Path to save the resulting numbering JSON")
    parser.add_argument("--output-overlay", type=Path, help="Path to save the visualization overlay PNG")
    parser.add_argument("--start-number", type=int, default=1, help="Starting measure number")
    parser.add_argument("--page-number", type=int, default=1, help="Page number for the input data")
    
    args = parser.parse_args()

    # Load barlines
    with open(args.barlines, 'r') as f:
        raw_barlines = json.load(f)
    barline_boxes = normalize_barlines(raw_barlines)

    # Get image size
    img_ref = cv2.imread(str(args.image))
    if img_ref is None:
        print(f"Error: Could not read reference image: {args.image}")
        sys.exit(1)
    h, w = img_ref.shape[:2]

    # Initialize Pipeline
    pipeline = MeasureNumberingPipeline()
    
    # Process
    page_data = {
        'barlines': barline_boxes,
        'staff_mask': args.staff_mask,
        'image_size': (w, h),
        'page_number': args.page_number,
        'image': img_ref
    }
    
    score = pipeline.run_sequential([page_data], start_number=args.start_number)

    # Save JSON
    if args.output_json:
        result_dict = score_to_dict(score)
        with open(args.output_json, 'w') as f:
            json.dump(result_dict, f, indent=2)
        print(f"Result JSON saved to: {args.output_json}")

    # Save Overlay
    if args.output_overlay:
        render_overlay(score, args.image, args.output_overlay)

if __name__ == "__main__":
    main()
