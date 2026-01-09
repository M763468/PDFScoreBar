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
    
    # Add dilation to thicken text
    kernel = np.ones((2,2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)
    
    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded

def detect_hbar(roi_img):
    """
    Detect if the ROI contains a rectangular horizontal bar (H-bar) characteristic of multi-measure rests.
    Returns: (bool found, rect tuple (x,y,w,h))
    """
    if roi_img is None or roi_img.size == 0: return False, None
    
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    h, w = binary.shape
    if w < 20 or h < 10: return False, None

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_rect = None
    
    # Staff center definitions
    v_center_min = h * 0.25
    v_center_max = h * 0.75
    
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        
        # 1. Aspect Ratio Check (Horizontal Bar)
        aspect_ratio = cw / float(ch)
        if aspect_ratio < 2.0:
            continue
            
        # 2. Area Check (Ignore speckles)
        if cw < w * 0.15: 
            continue
            
        # 3. Vertical Centering Check
        cy = y + ch / 2
        if not (v_center_min <= cy <= v_center_max):
            continue
            
        best_rect = (x, y, cw, ch)
        break # Found one
    
    return (best_rect is not None), best_rect

def extract_number_from_text(text):
    """
    Extract a valid multi-measure rest number from text.
    """
    if not text:
        return None
        
    # 1. Blacklist check
    blacklist = ["Viol", "Vc", "Cb", "Fl", "Ob", "Cl", "Fag", "Cor", "Tr", "Timp", "Pizz", "Arco", "Div", "Legni", "Solo", "Tutti", "con", "senza"]
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

def measure_residual_ink(roi_img, roi_staff_mask, hbar_rect, text_boxes, offset_x=0, offset_y=0):
    """
    Calculate the amount of ink remaining in the measure after removing:
    1. Staff lines (via mask)
    2. Detected H-Bar
    3. Detected Text (Numbers)
    
    hbar_rect: (x, y, w, h) relative to roi_img
    text_boxes: list of boxes, relative to roi_img (need adjustment if OCR ROI was different?)
                Assumption: text_boxes passed here are adjusted to be relative to roi_img.
    """
    if roi_img is None: return 999999
    
    # 1. Binarize Image (Ink = 255)
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 2. Remove Staff Lines
    kernel = np.ones((3,3), np.uint8)
    if roi_staff_mask is not None:
        # Resize mask if needed (should match roi_img size)
        if roi_staff_mask.shape != binary.shape:
             roi_staff_mask = cv2.resize(roi_staff_mask, (binary.shape[1], binary.shape[0]))
             
        staff_dilated = cv2.dilate(roi_staff_mask, kernel, iterations=1)
        # ink_no_staff = binary AND (NOT staff)
        ink_no_staff = cv2.bitwise_and(binary, cv2.bitwise_not(staff_dilated))
    else:
        ink_no_staff = binary.copy()

    # 3. Remove H-Bar (with margin)
    if hbar_rect:
        x, y, w, h = hbar_rect
        # Dilate the H-Bar removal area to catch anti-aliasing artifacts
        margin = 3
        cv2.rectangle(ink_no_staff, (max(0, x-margin), max(0, y-margin)), (min(ink_no_staff.shape[1], x+w+margin), min(ink_no_staff.shape[0], y+h+margin)), 0, -1) 
        
    # 4. Remove Text Boxes (with margin)
    if text_boxes:
        for box in text_boxes:
            # Expand box slightly
            pts = np.array(box, dtype=np.int32)
            
            # Create a mask for the text box and dilate it
            text_mask = np.zeros_like(ink_no_staff)
            cv2.fillPoly(text_mask, [pts], 255)
            kernel = np.ones((5,5), np.uint8) # Aggressive dilation for text removal
            text_mask_dilated = cv2.dilate(text_mask, kernel, iterations=1)
            
            # Remove text ink
            ink_no_staff = cv2.bitwise_and(ink_no_staff, cv2.bitwise_not(text_mask_dilated))
            
    # 5. Count remaining pixels
    residual = cv2.countNonZero(ink_no_staff)
    return residual

def draw_debug_info(debug_img, x1, y1, x2, y2, status, text="", details=""):
    """
    Draw rectangle and text on debug image.
    Status: 'found' (Green), 'rejected' (Red), 'skip' (Yellow)
    """
    if debug_img is None: return
    
    color = (0, 0, 255) # Red default
    if status == 'found':
        color = (0, 255, 0) # Green
    elif status == 'skip':
        color = (0, 255, 255) # Yellow
    
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
    
    label = f"{text}"
    if details:
        label += f" ({details})"
        
    cv2.putText(debug_img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def main():
    parser = argparse.ArgumentParser(description="Generate numbering overrides from multi-measure rest OCR.")
    parser.add_argument("--numbering-json", type=Path, required=True, help="Path to numbering JSON")
    parser.add_argument("--notehead-mask", type=Path, required=True, help="Path to notehead mask PNG")
    parser.add_argument("--staff-mask", type=Path, required=False, help="Path to staff mask PNG (Optional but recommended)")
    parser.add_argument("--image", type=Path, required=True, help="Path to original image")
    parser.add_argument("--output-overrides", type=Path, required=True, help="Path to save overrides JSON")
    parser.add_argument("--debug-image", type=Path, default=None, help="Path to save debug overlay image")
    parser.add_argument("--threshold", type=int, default=150, help="Max pixels of notehead to consider 'empty' (Legacy)")
    parser.add_argument("--ink-threshold", type=int, default=1500, help="Max residual ink pixels allowed")
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
    
    staff_mask = None
    if args.staff_mask:
        staff_mask = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
        if staff_mask is not None:
            _, staff_mask = cv2.threshold(staff_mask, 127, 255, cv2.THRESH_BINARY)
            
    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Error: Could not read image: {args.image}")
        sys.exit(1)

    debug_img = None
    if args.debug_image:
        debug_img = image.copy()

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
                
                # 1. Density Check (Legacy Notehead Mask)
                # Keep this as a fast first-pass filter
                margin_y_check_scaled = int(args.vertical_margin_check * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1_check = max(0, int(y1 * scale_y) - margin_y_check_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2_check = min(h_mask, int(y2 * scale_y) + margin_y_check_scaled)
                
                roi_mask = proc_mask[my1_check:my2_check, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)
                
                if pixel_count > args.threshold:
                     # draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', details=f"Ink: {pixel_count}")
                     continue

                # 2. H-Bar Check (Strict Margin)
                
                roi_x1 = max(0, x1 - 10)
                roi_x2 = min(w_img, x2 + 10)
                
                roi_y1_check = max(0, y1 - args.vertical_margin_check)
                roi_y2_check = min(h_img, y2 + args.vertical_margin_check)
                
                roi_img_check = image[roi_y1_check:roi_y2_check, roi_x1:roi_x2]
                
                if roi_img_check.size == 0:
                    continue
                
                # Refined H-Bar Check
                is_hbar, hbar_rect = detect_hbar(roi_img_check)
                if not is_hbar:
                    # draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', details="No H-Bar")
                    continue

                # 3. OCR (Relaxed Margin)
                
                roi_y1_ocr = max(0, y1 - args.vertical_margin_ocr)
                roi_y2_ocr = min(h_img, y2 + args.vertical_margin_check) 
                
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
                        valid_boxes_relative_to_ocr_roi = []
                        
                        for res in ocr_result:
                            box = res[0] # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                            text = res[1]
                            
                            # Calculate text center relative to ROI
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            text_center_x = sum(xs) / len(xs)
                            
                            # Calculate absolute coordinates for debug drawing
                            abs_x1 = roi_x1 + int(min(xs))
                            abs_y1 = roi_y1_ocr + int(min(ys))
                            abs_x2 = roi_x1 + int(max(xs))
                            abs_y2 = roi_y1_ocr + int(max(ys))
                            
                            # Spatial Filter: 
                            # A) Reject Left Edge (Rehearsal Marks)
                            is_left_edge = text_center_x < (roi_w * 0.15)
                            is_right_edge = text_center_x > (roi_w * 0.85)
                            
                            # B) Require Centering (Strict)
                            dist = abs(text_center_x - center_x)
                            is_centered = dist < (roi_w * 0.15)
                            
                            if is_left_edge or is_right_edge:
                                print(f"    [REJECT] '{text}': Edge (x={text_center_x:.1f}, w={roi_w})")
                                draw_debug_info(debug_img, abs_x1, abs_y1, abs_x2, abs_y2, 'rejected', text, "Edge")
                                continue
                                
                            if not is_centered:
                                print(f"    [REJECT] '{text}': Not Centered (dist={dist:.1f}, limit={roi_w*0.15:.1f})")
                                draw_debug_info(debug_img, abs_x1, abs_y1, abs_x2, abs_y2, 'rejected', text, "Not Centered")
                                continue

                            # Passed filters
                            valid_texts.append(text)
                            valid_boxes_relative_to_ocr_roi.append(box)

                        if valid_texts:
                            full_text = " ".join(valid_texts)
                            number = extract_number_from_text(full_text)
                            
                            if number:
                                # 4. RESIDUAL INK CHECK (Final Gate)
                                # Prepare arguments
                                # hbar_rect is relative to roi_img_check (which is same X range as roi_img_ocr, but different Y)
                                # We need to map everything to a common coordinate system or pass distinct ones.
                                # Let's use roi_img_check as the base for ink check, as it covers the staff area nicely.
                                # But OCR boxes are in roi_img_ocr (taller).
                                
                                # Let's perform ink check on the wider vertical ROI (roi_img_ocr) to catch everything.
                                # But we need staff_mask for that area.
                                
                                roi_staff_mask_full = None
                                if staff_mask is not None:
                                     # Ensure ROI is valid within staff_mask dimensions
                                     sy1 = max(0, roi_y1_ocr)
                                     sy2 = min(staff_mask.shape[0], roi_y2_ocr)
                                     sx1 = max(0, roi_x1)
                                     sx2 = min(staff_mask.shape[1], roi_x2)
                                     
                                     if sy2 > sy1 and sx2 > sx1:
                                        roi_staff_mask_full = staff_mask[sy1:sy2, sx1:sx2]
                                     else:
                                        roi_staff_mask_full = None

                                # Adjust H-Bar rect to roi_img_ocr coordinates
                                offset_y = roi_y1_check - roi_y1_ocr
                                hx, hy, hw, hh = hbar_rect
                                adjusted_hbar = (hx, hy + offset_y, hw, hh)
                                
                                residual_ink = measure_residual_ink(
                                    roi_img_ocr, 
                                    roi_staff_mask_full, 
                                    adjusted_hbar, 
                                    valid_boxes_relative_to_ocr_roi
                                )
                                
                                if residual_ink > args.ink_threshold:
                                    print(f"  [REJECT] P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' -> Residual Ink too high: {residual_ink} > {args.ink_threshold}")
                                    draw_debug_info(debug_img, x1, y1, x2, y2, 'rejected', f"{number}", f"Ink:{residual_ink}")
                                else:
                                    print(f"  [FOUND] P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' -> Count={number} (Ink={residual_ink})")
                                    
                                    overrides.append({
                                        "page": page_num - 1, 
                                        "system": sys_idx,
                                        "measure": m_idx,
                                        "skip": number - 1,
                                        "comment": f"Auto-detected multi-measure rest: {number}"
                                    })
                                    draw_debug_info(debug_img, x1, y1, x2, y2, 'found', f"Rest: {number}")
                            else:
                                print(f"  [SKIP]  P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' (Not a number)")
                                draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', f"NaN: {full_text}")

                except Exception as e:
                    print(f"  [ERROR] P{page_num} S{sys_idx} M{m_num}: {e}")

    # Output JSON
    output_data = {"measure_overrides": overrides}
    with open(args.output_overrides, 'w') as f:
        json.dump(output_data, f, indent=2)
    print(f"Saved {len(overrides)} overrides to {args.output_overrides}")

    # Output Image
    if args.debug_image and debug_img is not None:
        cv2.imwrite(str(args.debug_image), debug_img)
        print(f"Saved debug image to {args.debug_image}")

if __name__ == "__main__":
    main()