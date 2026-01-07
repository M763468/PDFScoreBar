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
    Apply preprocessing for OCR:
    - Grayscale
    - Otsu Thresholding
    - Inversion (to ensure Black text on White BG)
    - Denoising (Opening)
    - Padding
    """
    if img is None: return None
    
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
    Relaxed Policy:
    - Reject if contains Blacklisted words (Instruments, Techniques).
    - Accept if contains any integer >= 2.
    - If multiple integers, pick the largest one.
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
    
    # Return the largest valid number found
    return max(valid_nums)

def main():
    parser = argparse.ArgumentParser(description="Generate numbering overrides from multi-measure rest OCR.")
    parser.add_argument("--numbering-json", type=Path, required=True, help="Path to numbering JSON")
    parser.add_argument("--notehead-mask", type=Path, required=True, help="Path to notehead mask PNG")
    parser.add_argument("--image", type=Path, required=True, help="Path to original image")
    parser.add_argument("--output-overrides", type=Path, required=True, help="Path to save overrides JSON")
    parser.add_argument("--threshold", type=int, default=150, help="Max pixels of notehead to consider 'empty'")
    parser.add_argument("--vertical-margin-check", type=int, default=10, help="Vertical margin for Density/H-Bar check")
    parser.add_argument("--vertical-margin-ocr", type=int, default=80, help="Vertical margin for OCR")
    parser.add_argument("--erode-iter", type=int, default=1, help="Iterations of erosion")
    
    args = parser.parse_args()
    
    # Initialize OCR
    ocr_engine = RapidOCR()

    # Load data
    with open(args.numbering_json, 'r') as f:
        data = json.load(f)
    
    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"Error: Could not read mask: {args.notehead_mask}")
        sys.exit(1)
        
    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Error: Could not read image: {args.image}")
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

    overrides = []
    
    print("Scanning measures for multi-measure rests...")
    
    for page in data["pages"]:
        page_num = page['page_number']
        for sys_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                m_num = measure["number"]
                bbox = measure["bbox"]
                
                x1, y1, x2, y2 = bbox
                
                # 1. Density Check (Strict Margin)
                margin_y_check_scaled = int(args.vertical_margin_check * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1_check = max(0, int(y1 * scale_y) - margin_y_check_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2_check = min(h_mask, int(y2 * scale_y) + margin_y_check_scaled)
                
                roi_mask = proc_mask[my1_check:my2_check, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)
                
                if pixel_count <= args.threshold:
                    # 2. H-Bar Check (Strict Margin)
                    # Extract ROI from Image (not mask) using STRICT margin
                    
                    roi_x1 = max(0, x1 - 10)
                    roi_x2 = min(w_img, x2 + 10)
                    
                    roi_y1_check = max(0, y1 - args.vertical_margin_check)
                    roi_y2_check = min(h_img, y2 + args.vertical_margin_check)
                    
                    roi_img_check = image[roi_y1_check:roi_y2_check, roi_x1:roi_x2]
                    
                    if roi_img_check.size == 0:
                        continue
                    
                    if not detect_hbar(roi_img_check):
                        continue

                    # 3. OCR (Relaxed Margin)
                    # Use relaxed margin to capture numbers above staff
                    
                    roi_y1_ocr = max(0, y1 - args.vertical_margin_ocr)
                    # Dynamic bottom: 70% of height + 30px
                    roi_y2_ocr_limit = y1 + int((y2 - y1) * 0.7) + 30
                    roi_y2_ocr = min(h_img, roi_y2_ocr_limit)
                    
                    roi_img_ocr = image[roi_y1_ocr:roi_y2_ocr, roi_x1:roi_x2]

                    # Preprocess and OCR
                    proc_img = preprocess_image(roi_img_ocr)
                    try:
                        ocr_result, _ = ocr_engine(proc_img)
                        if ocr_result:
                            # Spatial Filtering & Text Aggregation
                            roi_w = proc_img.shape[1]
                            center_x = roi_w / 2
                            valid_texts = []
                            
                            for res in ocr_result:
                                box = res[0] # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                                text = res[1]
                                
                                # Calculate text center X
                                xs = [p[0] for p in box]
                                text_center_x = sum(xs) / len(xs)
                                
                                # Check distance from center (allow 10% deviation)
                                dist = abs(text_center_x - center_x)
                                if dist < (roi_w * 0.10):
                                    valid_texts.append(text)
                                else:
                                    print(f"    [IGNORE] Text '{text}' too far from center (dist={dist:.1f}, limit={roi_w*0.10:.1f})")

                            if valid_texts:
                                # Combine filtered text
                                full_text = " ".join(valid_texts)
                                
                                # Validate
                                number = extract_number_from_text(full_text)
                                
                                if number:
                                    print(f"  [FOUND] P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' -> Count={number}")
                                    
                                    overrides.append({
                                        "page": page_num - 1, 
                                        "system": sys_idx,
                                        "measure": m_idx,
                                        "skip": number - 1,
                                        "comment": f"Auto-detected multi-measure rest: {number}"
                                    })
                                else:
                                    print(f"  [SKIP]  P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' (Rejected)")
                            else:
                                print(f"  [SKIP]  P{page_num} S{sys_idx} M{m_num}: No text in center zone")
                        else:
                            # print(f"  [EMPTY] P{page_num} S{sys_idx} M{m_num}")
                            pass
                            
                    except Exception as e:
                        print(f"  [ERROR] P{page_num} S{sys_idx} M{m_num}: {e}")

    # Output
    output_data = {"measure_overrides": overrides}
    with open(args.output_overrides, 'w') as f:
        json.dump(output_data, f, indent=2)
        
    print(f"Saved {len(overrides)} overrides to {args.output_overrides}")

if __name__ == "__main__":
    main()