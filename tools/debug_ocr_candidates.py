import argparse
import json
import cv2
import numpy as np
from pathlib import Path
import sys
from rapidocr_onnxruntime import RapidOCR

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def preprocess_image(img):
    """
    Apply preprocessing for OCR (same as generate_numbering_overrides.py)
    """
    if img is None or img.size == 0: return None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_white_bg = cv2.bitwise_not(binary)
    
    kernel = np.ones((2,2), np.uint8)
    opened = cv2.morphologyEx(binary_white_bg, cv2.MORPH_OPEN, kernel)
    
    padded = cv2.copyMakeBorder(opened, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded

def main():
    parser = argparse.ArgumentParser(description="Visualize OCR candidates and results.")
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--notehead-mask", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=50)
    parser.add_argument("--vertical-margin", type=int, default=80)
    parser.add_argument("--erode-iter", type=int, default=1)
    
    args = parser.parse_args()
    ensure_dir(args.output_image.parent)
    
    # Initialize OCR
    ocr_engine = RapidOCR()

    # Load data
    with open(args.numbering_json, 'r') as f:
        data = json.load(f)
    
    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    image = cv2.imread(str(args.image))
    
    if mask is None or image is None:
        print("Error loading images")
        sys.exit(1)

    h_img, w_img = image.shape[:2]
    h_mask, w_mask = mask.shape[:2]
    scale_x = w_mask / w_img
    scale_y = h_mask / h_img

    # Mask Preprocessing
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if args.erode_iter > 0:
        kernel = np.ones((3,3), np.uint8)
        proc_mask = cv2.erode(bin_mask, kernel, iterations=args.erode_iter)
    else:
        proc_mask = bin_mask

    # Draw on copy of image
    vis_img = image.copy()
    
    # Pre-calculate font scale based on image width
    font_scale = max(0.5, w_img / 2000.0) 
    thickness = max(1, int(font_scale * 2))

    print(f"Scanning measures with threshold {args.threshold}...")
    
    for page in data["pages"]:
        for system in page["systems"]:
            for measure in system["measures"]:
                m_num = measure["number"]
                bbox = measure["bbox"]
                x1, y1, x2, y2 = bbox
                
                # Check emptiness
                margin_y_scaled = int(args.vertical_margin * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1 = max(0, int(y1 * scale_y) - margin_y_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2 = min(h_mask, int(y2 * scale_y) + margin_y_scaled)
                
                # Clamp
                mx1 = max(0, mx1); my1 = max(0, my1)
                mx2 = min(w_mask, mx2); my2 = min(h_mask, my2)
                
                roi_mask = proc_mask[my1:my2, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)
                
                if pixel_count <= args.threshold:
                    # ROI Extraction (Expanded)
                    x_margin = 10
                    roi_x1 = max(0, x1 - x_margin)
                    roi_x2 = min(w_img, x2 + x_margin)
                    
                    roi_y1 = max(0, y1 - 30)
                    roi_y2_limit = y1 + int((y2 - y1) * 0.7) + 30
                    roi_y2 = min(h_img, roi_y2_limit)
                    
                    roi_img = image[roi_y1:roi_y2, roi_x1:roi_x2]
                    
                    ocr_text = "(Fail)"
                    if roi_img.size > 0:
                        proc_img = preprocess_image(roi_img)
                        try:
                            ocr_result, _ = ocr_engine(proc_img)
                            if ocr_result:
                                ocr_text = " ".join([res[1] for res in ocr_result])
                            else:
                                ocr_text = "(No Text)"
                        except:
                            ocr_text = "(Err)"
                    
                    # Visualization
                    # Red Box for ROI
                    cv2.rectangle(vis_img, (x1, roi_y1), (x2, roi_y2), (0, 0, 255), 2)
                    
                    # Info Text
                    info = f"px:{pixel_count} | {ocr_text}"
                    
                    # Draw text background
                    (tw, th), _ = cv2.getTextSize(info, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                    cv2.rectangle(vis_img, (x1, roi_y1 - th - 5), (x1 + tw, roi_y1), (255, 255, 255), -1)
                    cv2.putText(vis_img, info, (x1, roi_y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 0, 0), thickness)

    cv2.imwrite(str(args.output_image), vis_img)
    print(f"Saved visualization to {args.output_image}")

if __name__ == "__main__":
    main()
