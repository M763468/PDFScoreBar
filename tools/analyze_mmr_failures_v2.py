
import argparse
import json
import cv2
import numpy as np
import re
from pathlib import Path
from rapidocr_onnxruntime import RapidOCR

def preprocess_image_ocr(img):
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_white_bg = cv2.bitwise_not(binary)
    kernel = np.ones((2,2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)
    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded

def detect_hbar_centroid(img):
    if img is None: return False, None, None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    h, w = binary.shape
    if w < 10: return False, None, None
    
    k_width = max(15, int(w * 0.3))
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
    
    thick_kernel = np.ones((3, 1), np.uint8)
    thick_lines = cv2.erode(detected_lines, thick_kernel, iterations=1)
    
    moments = cv2.moments(thick_lines)
    if moments["m00"] > 50: 
        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
        return True, cx, cy
    return False, None, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", action="append", help="Format: work:page:measure_index (e.g. Sibelius:3:22)")
    parser.add_argument("--output-dir", type=Path, default=Path("logs/experiments/failure_analysis_v2"))
    # Default paths (can be overriden or inferred)
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--numbering-root", type=Path, default=Path("logs/experiments/global_mmr_eval_v3_ocr_fix_crop")) 
    
    args = parser.parse_args()
    
    ocr_engine = RapidOCR()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    targets = []
    for t in args.target:
        parts = t.split(":")
        if len(parts) == 3:
            # work:page:measure_index
            work = parts[0]
            # Fuzzy match work name
            work_low = work.lower()
            if "sibelius" in work_low: work = "Sibelius-Violin_Concerto-Viola"
            elif "prokofiev5" in work_low or "prok5" in work_low: work = "prokofiev5"
            elif "prok1" in work_low or "prokofiev1" in work_low: work = "Va_Prokofiev_Symphony1"
            elif "festival" in work_low: work = "Shostakovich-Festival_Overture_Va"
            elif "sym5" in work_low: work = "Shosrakovich-Sym5-Va"
            
            page = int(parts[1])
            m_idx = int(parts[2])
            targets.append((work, page, m_idx))
            
    # Process
    for work, page_num, target_m_idx in targets:
        print(f"Analyzing {work} Page {page_num} Measure {target_m_idx}...")
        
        page_str = f"page_{page_num:03d}"
        img_path = args.image_root / work / f"{page_str}.png"
        num_json = args.numbering_root / work / page_str / "numbering_initial.json" # Use initial to get pure bboxes
        
        if not img_path.exists() or not num_json.exists():
            print(f"  Missing files: {img_path} or {num_json}")
            continue
            
        image = cv2.imread(str(img_path))
        with open(num_json) as f:
            data = json.load(f)
            
        # Find measure
        measure = None
        sys_idx = -1
        
        # Flatten measure list to find by global index? Or assume system/measure structure?
        # The target_m_idx from user is likely 0-based index in the page's measure list
        # Let's flatten
        all_measures = []
        for s_i, system in enumerate(data['pages'][0]['systems']):
            for m_i, m in enumerate(system['measures']):
                m['system_index'] = s_i
                all_measures.append(m)
                
        if target_m_idx < len(all_measures):
            measure = all_measures[target_m_idx]
        
        if not measure:
            print("  Measure not found")
            continue
            
        bbox = measure['bbox']
        x1, y1, x2, y2 = map(int, bbox)
        
        # 1. Context Crop
        pad = 100
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(image.shape[1], x2 + pad)
        cy2 = min(image.shape[0], y2 + pad)
        
        context_img = image[cy1:cy2, cx1:cx2].copy()
        
        # Draw Measure Box
        cv2.rectangle(context_img, (x1-cx1, y1-cy1), (x2-cx1, y2-cy1), (255, 0, 0), 2)
        
        # 2. OCR Crops & Analysis
        # Replicate v3/v4 logic
        margin_y = 80
        ox1 = max(0, x1 - 30)
        ox2 = min(image.shape[1], x2 + 30)
        oy1 = max(0, y1 - margin_y)
        oy2 = min(image.shape[0], y2 + 80)
        
        ocr_crop = image[oy1:oy2, ox1:ox2]
        
        # H-Bar Analysis (Tighter vertical crop for H-bar)
        hy1 = max(0, y1 - 10)
        hy2 = min(image.shape[0], y2 + 10)
        hbar_crop = image[hy1:hy2, ox1:ox2]
        
        has_hbar, hbar_cx, hbar_cy = detect_hbar_centroid(hbar_crop)
        
        # OCR
        proc_img = preprocess_image_ocr(ocr_crop)
        ocr_res, _ = ocr_engine(proc_img)
        
        # Visualization on Context
        # Map OCR coords back to Context Image
        ocr_origin_x = ox1 - cx1
        ocr_origin_y = oy1 - cy1
        
        # Draw OCR Crop Box
        cv2.rectangle(context_img, (ox1-cx1, oy1-cy1), (ox2-cx1, oy2-cy1), (0, 255, 0), 1)
        
        if has_hbar:
            # Map HBar centroid to Context
            # hbar_crop origin relative to Context:
            hbar_origin_x = ox1 - cx1
            hbar_origin_y = hy1 - cy1
            
            hcx_global = int(hbar_origin_x + hbar_cx)
            hcy_global = int(hbar_origin_y + hbar_cy)
            
            # Draw HBar Centroid
            cv2.circle(context_img, (hcx_global, hcy_global), 5, (0, 0, 255), -1)
            # Draw HBar Anchor Line
            cv2.line(context_img, (0, hcy_global), (context_img.shape[1], hcy_global), (0, 0, 255), 1)
            
        # Draw Image Center Line (Blue)
        measure_cy = (y1 + y2) // 2 - cy1
        cv2.line(context_img, (0, measure_cy), (context_img.shape[1], measure_cy), (255, 0, 0), 1)
        
        # Draw OCR Results
        if ocr_res:
            crop_h, crop_w = proc_img.shape[:2]
            crop_cx = crop_w / 2.0
            crop_cy = crop_h / 2.0
            
            for item in ocr_res:
                box, text, score = item
                # box is in proc_img coords
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                box_cx = sum(xs) / len(xs)
                box_cy = sum(ys) / len(ys)
                
                # Metrics
                dist_x_norm = abs(box_cx - crop_cx) / crop_w
                dist_y_norm = abs(box_cy - crop_cy) / crop_h
                
                hbar_dist_str = ""
                if has_hbar:
                    # hbar_cy is relative to hbar_crop (which has different Y origin than ocr_crop!)
                    # Map both to global (Context) or align them
                    # ocr_crop Y: oy1
                    # hbar_crop Y: hy1
                    
                    # Global Y
                    box_cy_global = oy1 + (box_cy - 20) # Remove padding(20) approx
                    hbar_cy_global = hy1 + hbar_cy
                    
                    hbar_dist = abs(box_cy_global - hbar_cy_global)
                    hbar_dist_norm = hbar_dist / crop_h
                    hbar_dist_str = f", hbar_dy={hbar_dist_norm:.2f}"

                print(f"    OCR: '{text}' (conf={score:.2f}, dx={dist_x_norm:.2f}, dy={dist_y_norm:.2f}{hbar_dist_str})")
                
                # Try mapping: Padded(20) -> Dilated -> Binary -> Gray -> Crop
                # Coord - 20 = Crop Coord
                
                poly = np.array(box).astype(np.int32)
                poly -= 20 # Remove padding
                poly[:, 0] += ocr_origin_x
                poly[:, 1] += ocr_origin_y
                
                cv2.polylines(context_img, [poly], True, (0, 255, 255), 1)
                cv2.putText(context_img, f"{text}", (poly[0][0], poly[0][1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Save
        out_name = f"{work}_P{page_num}_M{target_m_idx}"
        cv2.imwrite(str(args.output_dir / f"{out_name}_context.png"), context_img)
        cv2.imwrite(str(args.output_dir / f"{out_name}_ocr_crop.png"), ocr_crop)
        if has_hbar:
             cv2.imwrite(str(args.output_dir / f"{out_name}_hbar_crop.png"), hbar_crop)
             
        print(f"  Saved to {args.output_dir}/{out_name}_*.png")

if __name__ == "__main__":
    main()
