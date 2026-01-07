import argparse
import json
import cv2
import numpy as np
from pathlib import Path
import sys
import re
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
    
    # Removed denoising to prevent erasing thin numbers
    # kernel = np.ones((2,2), np.uint8)
    # opened = cv2.morphologyEx(binary_white_bg, cv2.MORPH_OPEN, kernel)
    
    # Add dilation to thicken text
    kernel = np.ones((2,2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)
    
    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded

def detect_hbar(roi_img):
    """
    Detect if the ROI contains a horizontal bar (H-bar) characteristic of multi-measure rests.
    """
    if roi_img is None or roi_img.size == 0: return False
    
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    h, w = binary.shape
    if w < 20: return False
    
    # Kernel: Long horizontal line (30% of width)
    k_width = max(15, int(w * 0.3)) 
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, 1))
    
    # Detect lines
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
    
    # Check for significant pixels
    count = cv2.countNonZero(detected_lines)
    
    # Threshold: meaningful line segment found
    return count > 20

def extract_number_from_text(text):
    """
    Extract a valid multi-measure rest number from text.
    """
    if not text:
        return None
        
    # 1. Blacklist check
    blacklist = ["Viol", "Vc", "Cb", "Fl", "Ob", "Cl", "Fag", "Cor", "Tr", "Timp", "Pizz", "Arco", "Div", "Legni", "Solo", "Tutti"]
    for word in blacklist:
        if word.lower() in text.lower():
            return None 
    
    # 2. Extract all digit sequences
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return None
    
    # 3. Pick best number
    valid_nums = []
    for n_str in numbers:
        try:
            val = int(n_str)
            if val >= 2:
                valid_nums.append(val)
        except:
            pass
            
    if not valid_nums:
        return None
    
    return max(valid_nums)

def main():
    parser = argparse.ArgumentParser(description="Visualize OCR candidates and results.")
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--notehead-mask", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--vertical-margin-check", type=int, default=10)
    parser.add_argument("--vertical-margin-ocr", type=int, default=80)
    parser.add_argument("--erode-iter", type=int, default=1)
    parser.add_argument("--force-measure", type=int, nargs='+', help="Force OCR on these measure numbers")
    
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
                
                force_check = args.force_measure and m_num in args.force_measure

                # 1. Density Check (Strict)
                margin_y_check_scaled = int(args.vertical_margin_check * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1_check = max(0, int(y1 * scale_y) - margin_y_check_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2_check = min(h_mask, int(y2 * scale_y) + margin_y_check_scaled)
                
                roi_mask = proc_mask[my1_check:my2_check, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)
                
                if force_check:
                    print(f"  [FORCE] M{m_num} Density Check: Px={pixel_count} (Limit={args.threshold})")

                if pixel_count <= args.threshold or force_check:
                    
                    # 2. H-Bar Check (Strict)
                    roi_x1 = max(0, x1 - 10)
                    roi_x2 = min(w_img, x2 + 10)
                    roi_y1_check = max(0, y1 - args.vertical_margin_check)
                    roi_y2_check = min(h_img, y2 + args.vertical_margin_check)
                    roi_img_check = image[roi_y1_check:roi_y2_check, roi_x1:roi_x2]
                    
                    has_hbar = detect_hbar(roi_img_check)
                    
                    if force_check:
                        print(f"  [FORCE] M{m_num} H-Bar Check: {has_hbar}")
                        debug_roi_path = Path(args.output_image).parent / f"roi_M{m_num}_hbar.png"
                        if roi_img_check.size > 0:
                            cv2.imwrite(str(debug_roi_path), roi_img_check)

                    if has_hbar or force_check:
                        # 3. OCR (Relaxed)
                        roi_y1_ocr = max(0, y1 - args.vertical_margin_ocr)
                        roi_y2_ocr_limit = y1 + int((y2 - y1) * 0.7) + 30
                        roi_y2_ocr = min(h_img, roi_y2_ocr_limit)
                        roi_img_ocr = image[roi_y1_ocr:roi_y2_ocr, roi_x1:roi_x2]
                        
                        if force_check:
                            debug_ocr_path = Path(args.output_image).parent / f"roi_M{m_num}_ocr.png"
                            cv2.imwrite(str(debug_ocr_path), roi_img_ocr)

                        # Visualization: Draw both ROIs (Cyan=Check, Red=OCR)
                        cv2.rectangle(vis_img, (roi_x1, roi_y1_check), (roi_x2, roi_y2_check), (255, 255, 0), 1) # Cyan
                        cv2.rectangle(vis_img, (roi_x1, roi_y1_ocr), (roi_x2, roi_y2_ocr), (0, 0, 255), 2) # Red
                        
                        status_text = ""
                        color = (100, 100, 100)

                        if roi_img_ocr.size > 0:
                            proc_img = preprocess_image(roi_img_ocr)
                            try:
                                ocr_result, _ = ocr_engine(proc_img)
                                if ocr_result:
                                    roi_w = proc_img.shape[1]
                                    center_x = roi_w / 2
                                    valid_texts = []
                                    rejected_texts = []
                                    
                                    for res in ocr_result:
                                        box = res[0]
                                        text = res[1]
                                        score = res[2]
                                        
                                        xs = [p[0] for p in box]
                                        text_center_x = sum(xs) / len(xs)
                                        
                                        # Check distance from center (allow 10% deviation)
                                        dist = abs(text_center_x - center_x)
                                        is_centered = dist < (roi_w * 0.10)
                                        
                                        if force_check:
                                            print(f"    [OCR] '{text}' score={score:.2f} dist={dist:.1f}/{roi_w*0.10:.1f} centered={is_centered}")
                                        
                                        if is_centered:
                                            valid_texts.append(text)
                                        else:
                                            rejected_texts.append(text)

                                    full_valid_text = " ".join(valid_texts)
                                    number = extract_number_from_text(full_valid_text)
                                    
                                    if number:
                                        status_text = f"FOUND: {number} (hbar={has_hbar})"
                                        color = (0, 255, 0) # Green
                                        print(f"  [DEBUG] M{m_num} FOUND: {number} | HBar={has_hbar}")
                                    else:
                                        status_text = f"REJ: '{full_valid_text}' (hbar={has_hbar})"
                                        color = (0, 165, 255) # Orange
                                        print(f"  [DEBUG] M{m_num} REJECTED TEXT: '{full_valid_text}' | HBar={has_hbar}")
                                else:
                                    status_text = f"No Text (hbar={has_hbar})"
                                    color = (200, 200, 200)
                                    print(f"  [DEBUG] M{m_num} NO TEXT | HBar={has_hbar}")
                            except Exception as e:
                                status_text = f"Err (hbar={has_hbar})"
                                color = (0, 0, 255)
                                print(f"  [DEBUG] M{m_num} ERROR: {e}")
                        
                        # Info Text
                        info = f"M{m_num} Px:{pixel_count} | {status_text}"
                        (tw, th), _ = cv2.getTextSize(info, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                        cv2.rectangle(vis_img, (roi_x1, roi_y1_ocr - th - 5), (roi_x1 + tw, roi_y1_ocr), (255, 255, 255), -1)
                        cv2.putText(vis_img, info, (roi_x1, roi_y1_ocr - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)

    cv2.imwrite(str(args.output_image), vis_img)
    print(f"Saved visualization to {args.output_image}")

if __name__ == "__main__":
    main()