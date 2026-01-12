
import argparse
import json
import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
from pathlib import Path
import sys
import re
from rapidocr_onnxruntime import RapidOCR

# --- Model Definition (Must match training) ---
def load_model(model_path, device):
    model = models.resnet18(pretrained=False) # No need to download weights, we load state_dict
    model.fc = nn.Linear(model.fc.in_features, 1)
    
    # Load weights
    try:
        state_dict = torch.load(model_path, map_location=device)
        model.load_state_dict(state_dict)
    except Exception as e:
        print(f"Error loading model from {model_path}: {e}")
        # Identify if keys mismatch (e.g. 'module.' prefix)
        sys.exit(1)
        
    model = model.to(device)
    model.eval()
    return model

# --- Preprocessing for Model ---
# Must match training transforms (val)
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def predict_crop(model, cv2_img, device):
    """
    Returns probability of being a Rest (Label 1).
    """
    if cv2_img is None or cv2_img.size == 0:
        return 0.0
        
    # Convert CV2 (BGR) to PIL (RGB)
    img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    
    input_tensor = transform(pil_img).unsqueeze(0).to(device)
    
    with torch.no_grad():
        output = model(input_tensor)
        prob = torch.sigmoid(output).item()
        
    return prob

# --- OCR Helpers (Reused) ---
def preprocess_image_ocr(img):
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_white_bg = cv2.bitwise_not(binary)
    kernel = np.ones((2,2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)
    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded

def merge_ocr_results(ocr_result):
    """
    Merges horizontally adjacent OCR boxes that likely form a single number.
    e.g. Box("2") + Box("5") -> Box("25")
    """
    if not ocr_result or len(ocr_result) < 2:
        return ocr_result

    # Sort by X coordinate (left to right)
    # box[0] is points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    # sort by min x
    ocr_result.sort(key=lambda x: min([p[0] for p in x[0]]))

    merged = []
    current_box = ocr_result[0]

    for next_box in ocr_result[1:]:
        # unpack current
        c_pts, c_txt, c_conf = current_box
        c_xs = [p[0] for p in c_pts]
        c_ys = [p[1] for p in c_pts]
        c_x2, c_y1, c_y2 = max(c_xs), min(c_ys), max(c_ys)
        c_h = c_y2 - c_y1

        # unpack next
        n_pts, n_txt, n_conf = next_box
        n_xs = [p[0] for p in n_pts]
        n_ys = [p[1] for p in n_pts]
        n_x1, n_y1, n_y2 = min(n_xs), min(n_ys), max(n_ys)
        n_h = n_y2 - n_y1

        # Criteria for merge:
        # 1. Vertical alignment (centers close or significant overlap)
        c_cy = (c_y1 + c_y2) / 2
        n_cy = (n_y1 + n_y2) / 2
        vertical_aligned = abs(c_cy - n_cy) < (min(c_h, n_h) * 0.5)

        # 2. Horizontal proximity (gap small relative to height)
        gap = n_x1 - c_x2
        # Allow small negative gap (overlap) or small positive gap
        horizontal_close = gap < (min(c_h, n_h) * 0.3) # Stricter gap for digits

        # 3. Height similarity (digits in a number should have similar heights)
        height_diff = abs(c_h - n_h) / max(c_h, n_h)
        height_similar = height_diff < 0.2 # Allow up to 20% diff
        
        # 4. Content is digits
        txt_merged = c_txt + n_txt
        is_digit_pattern = bool(re.match(r'^\d+$', txt_merged))

        if vertical_aligned and horizontal_close and height_similar and is_digit_pattern:
            # Merge!
            # New box points: min_x, min_y, max_x, max_y
            mx1 = min(c_xs + n_xs)
            my1 = min(c_ys + n_ys)
            mx2 = max(c_xs + n_xs)
            my2 = max(c_ys + n_ys)
            
            # Reconstruct rapidocr box format: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            new_pts = [[mx1, my1], [mx2, my1], [mx2, my2], [mx1, my2]]
            new_conf = (c_conf + n_conf) / 2
            
            current_box = [new_pts, txt_merged, new_conf]
        else:
            merged.append(current_box)
            current_box = next_box
    
    merged.append(current_box)
    return merged

def select_best_candidate(ocr_result, img_width, img_height):
    """
    Selects the best number candidate based on geometric properties.
    Returns: (value, score, debug_string)
    """
    if not ocr_result:
        return None, 0, None

    # Step 0: Merge fragmented numbers
    ocr_result = merge_ocr_results(ocr_result)

    candidates = []
    center_x = img_width / 2.0
    
    blacklist = ["Viol", "Vc", "Cb", "Fl", "Ob", "Cl", "Fag", "Cor", "Tr", "Timp", "Pizz", "Arco", "Div", "Legni", "Solo", "Tutti", "con", "senza", "Allegro", "Adagio", "Andante", "Lento", "Presto", "Moderato"]

    for item in ocr_result:
        # Structure: [box_points, text, score]
        box_points = item[0]
        text = item[1]
        
        # Text filtering
        if any(b.lower() in text.lower() for b in blacklist):
            continue
            
        # Extract numbers
        # We look for all integers >= 2
        nums_found = re.findall(r'\d+', text)
        if not nums_found:
            continue
        
        # Geometric Analysis of the box
        xs = [p[0] for p in box_points]
        ys = [p[1] for p in box_points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        
        box_h = y_max - y_min
        box_center_x = (x_min + x_max) / 2.0
        box_center_y = (y_min + y_max) / 2.0
        
        # Metrics
        dist_x_norm = abs(box_center_x - center_x) / img_width
        dist_y_norm = abs(box_center_y - (img_height / 2.0)) / img_height
        h_ratio = box_h / img_height
        
        # For each number found in this text block, create a candidate
        for n_str in nums_found:
            try:
                val = int(n_str)
                if val < 2: continue
                
                # Scoring (Base 100)
                score = 100
                
                # 1. Horizontal Centering Penalty (Heavy)
                score -= dist_x_norm * 200 
                
                # 2. Vertical Centering Penalty (New)
                # Rest counts are strictly centered vertically on the stave.
                score -= dist_y_norm * 100

                # 3. Size Bonus/Penalty
                if 0.4 <= h_ratio <= 0.95:
                    score += 20
                elif h_ratio < 0.3:
                    score -= 30 
                    
                # 4. Tempo Mark Penalty (New)
                # If '=' is present and this number is likely part of the tempo mark
                # (e.g. "= 104", "M.M. 120")
                if "=" in text:
                    # If the number appears after '=', it's almost certainly a tempo mark
                    parts = text.split("=")
                    if len(parts) > 1 and n_str in parts[1]:
                        score -= 80 # Heavy penalty
                
                # 5. Length penalty for large numbers that don't fit typical MMR distributions
                if val > 100:
                    score -= 50

                candidates.append({
                    'val': val,
                    'score': score,
                    'debug': f"dx={dist_x_norm:.2f},dy={dist_y_norm:.2f},h={h_ratio:.2f}"
                })
            except: pass
        
    if not candidates:
        return None, 0, None
        
    candidates.sort(key=lambda x: x['score'], reverse=True)
    best = candidates[0]
    
    return best['val'], best['score'], best['debug']

def extract_number_from_text(text):
    if not text: return None
    blacklist = ["Viol", "Vc", "Cb", "Fl", "Ob", "Cl", "Fag", "Cor", "Tr", "Timp", "Pizz", "Arco", "Div", "Legni", "Solo", "Tutti", "con", "senza"]
    for word in blacklist:
        if word.lower() in text.lower(): return None 
    numbers = re.findall(r'\d+', text)
    if not numbers: return None
    valid_nums = []
    for n_str in numbers:
        try:
            val = int(n_str)
            if val >= 2: valid_nums.append(val)
        except: pass
    if not valid_nums: return None
    return max(valid_nums)

def draw_debug_info(debug_img, x1, y1, x2, y2, status, text="", details=""):
    if debug_img is None: return
    color = (0, 0, 255) 
    if status == 'found': color = (0, 255, 0)
    elif status == 'rescue': color = (0, 165, 255) # Orange for rescue
    elif status == 'skip': color = (0, 255, 255)
    
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
    label = f"{text} ({details})" if details else text
    cv2.putText(debug_img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def main():
    parser = argparse.ArgumentParser()
    # Required
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-overrides", type=Path, required=True)
    
    # CNN Specific
    parser.add_argument("--model-path", type=Path, default=None)
    
    # Legacy / Ignored
    parser.add_argument("--notehead-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--staff-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--vertical-margin-check", type=int, default=10, help="Legacy ignored")
    parser.add_argument("--vertical-margin-ocr", type=int, default=80, help="Legacy ignored")
    parser.add_argument("--erode-iter", type=int, default=1, help="Legacy ignored")
    parser.add_argument("--debug-image", type=Path, default=None)
    
    # Threshold handling
    parser.add_argument("--threshold", type=float, default=0.5, help="High Confidence Threshold")
    parser.add_argument("--rescue-threshold", type=float, default=0.1, help="Low Confidence Rescue Threshold")
    
    args = parser.parse_args()
    
    # Handle Threshold
    threshold = args.threshold
    rescue_threshold = args.rescue_threshold
    
    if threshold > 1.0:
        print(f"Warning: Legacy threshold {threshold} detected. Using default 0.5 for CNN.")
        threshold = 0.5
        
    # --- Model Loading ---
    model_path = args.model_path
    if model_path is None:
        # Try default locations
        search_paths = [
            Path("tools/mmr_training/models/mmr_classifier_best.pth"),
            Path("mmr_classifier_best.pth"),
            Path(__file__).parent / "mmr_training/models/mmr_classifier_best.pth",
            Path("/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/tools/mmr_training/models/mmr_classifier_best.pth")
        ]
        for p in search_paths:
            if p.exists():
                model_path = p
                break
    
    if model_path is None or not model_path.exists():
        print(f"Error: Model not found. Searched: {search_paths if args.model_path is None else [args.model_path]}")
        sys.exit(1)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    model = load_model(model_path, device)
    print("Model loaded.")
    
    # Initialize OCR
    ocr_engine = RapidOCR()
    
    # Load Data
    with open(args.numbering_json, 'r') as f:
        data = json.load(f)
        
    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Error reading image: {args.image}")
        sys.exit(1)
        
    h_img, w_img = image.shape[:2]
    
    debug_img = None
    if args.debug_image:
        debug_img = image.copy()
        
    overrides = []
    
    print("Running CNN Inference...")
    
    for page in data["pages"]:
        page_num = page['page_number']
        for sys_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                m_num = measure["number"]
                bbox = measure["bbox"]
                x1, y1, x2, y2 = bbox
                
                # Crop with margin (match training)
                margin = 20
                cx1 = max(0, x1 - margin)
                cy1 = max(0, y1 - margin)
                cx2 = min(w_img, x2 + margin)
                cy2 = min(h_img, y2 + margin)
                
                crop = image[cy1:cy2, cx1:cx2]
                
                # 1. CNN Prediction
                prob = predict_crop(model, crop, device)
                
                # LOGIC: Rescue Threshold allows entering OCR stage even with lower prob
                if prob > rescue_threshold:
                    # Candidate for Multi-measure Rest (Potential)
                    
                    # 2. RUN OCR (REFINED)
                    staves = system.get("staves", [])
                    stave_results = []
                    
                    for s_idx_local, stave in enumerate(staves):
                        s_bbox = stave["bbox"]
                        margin_y = 80 # Match analysis script for higher recall
                        sy1, sy2 = s_bbox[1], s_bbox[3]
                        
                        ox1 = max(0, x1 - 10)
                        ox2 = min(w_img, x2 + 10)
                        oy1 = max(0, sy1 - margin_y)
                        oy2 = min(h_img, sy2 + 10)
                        
                        stave_crop = image[oy1:oy2, ox1:ox2]
                        proc_img = preprocess_image_ocr(stave_crop)
                        if proc_img is None: continue
                        
                        ocr_res, _ = ocr_engine(proc_img)
                        
                        # Use new geometric selection
                        # crop size is passed to normalize coordinates
                        found_num, geo_score, dbg = select_best_candidate(ocr_res, ox2-ox1, oy2-oy1)
                        if found_num:
                            stave_results.append((found_num, geo_score, dbg))
                    
                    # Selection Logic
                    found_number = None
                    final_score = 0
                    final_debug = ""
                    
                    if stave_results:
                        # Sort by Score first? Or Vote?
                        # Voting is safer for multi-stave consistencies
                        from collections import Counter
                        nums = [r[0] for r in stave_results]
                        counts = Counter(nums)
                        found_number = counts.most_common(1)[0][0]
                        
                        # Get best score for this number
                        best_entry = max([r for r in stave_results if r[0] == found_number], key=lambda x: x[1])
                        final_score = best_entry[1]
                        final_debug = best_entry[2]
                        
                        # LOGICAL CHECK: Width vs Number
                        m_width = x2 - x1
                        if found_number > 20 and m_width < 100:
                            print(f"  [REJECTED] P{page_num} S{sys_idx} M{m_num}: Number {found_number} too large for width {m_width}")
                            found_number = None
                    
                    # 3. DECISION: High Confidence vs Rescue
                    is_valid_detection = False
                    status_label = ""
                    
                    if found_number:
                        if prob > threshold:
                            # High Confidence: Accept whatever number we found (unless rejected by logic)
                            is_valid_detection = True
                            status_label = "found"
                        elif final_score > 60: 
                            # Rescue Zone (0.1 < prob < 0.5)
                            # Only accept if Geometric Score is High (e.g. > 60 is decent, >80 is great)
                            # 100 is max. Centering penalty can drop it.
                            is_valid_detection = True
                            status_label = "rescue"
                            print(f"  [RESCUE] P{page_num} S{sys_idx} M{m_num}: Low Prob {prob:.2f} rescued by High OCR Score {final_score:.1f}")
                    
                    if is_valid_detection:
                        print(f"  [FOUND] P{page_num} S{sys_idx} M{m_num}: Prob={prob:.2f} -> OCR={found_number} (Score={final_score:.1f}, {final_debug})")
                        overrides.append({
                            "page": page_num - 1, 
                            "system": sys_idx,
                            "measure": m_idx,
                            "skip": found_number - 1,
                            "comment": f"CNN({prob:.2f})+OCR({final_score:.1f}): {found_number}"
                        })
                        draw_debug_info(debug_img, x1, y1, x2, y2, status_label, f"R{found_number}", f"P{prob:.2f} S{final_score:.0f}")
                    else:
                        # Only log "CHECK" if high prob but no OCR, otherwise it's just noise
                        if prob > threshold:
                            print(f"  [CHECK] P{page_num} S{sys_idx} M{m_num}: Prob={prob:.2f} -> No Valid OCR Number")
                            draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', f"CNN-only", f"{prob:.2f}")
                else:
                    # Normal measure (Very low prob)
                    pass

    # Save
    with open(args.output_overrides, 'w') as f:
        json.dump({"measure_overrides": overrides}, f, indent=2)
        
    if debug_img is not None and args.debug_image:
        cv2.imwrite(str(args.debug_image), debug_img)

if __name__ == "__main__":
    main()
