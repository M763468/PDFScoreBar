
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
    parser.add_argument("--model-path", type=Path, default=Path("mmr_classifier_best.pth"))
    
    # Legacy / Ignored
    parser.add_argument("--notehead-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--staff-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--vertical-margin-check", type=int, default=10, help="Legacy ignored")
    parser.add_argument("--vertical-margin-ocr", type=int, default=80, help="Legacy ignored")
    parser.add_argument("--erode-iter", type=int, default=1, help="Legacy ignored")
    parser.add_argument("--debug-image", type=Path, default=None)
    
    # Threshold handling
    parser.add_argument("--threshold", type=float, default=0.5, help="Prob threshold (if > 1.0 treated as legacy and ignored)")
    
    args = parser.parse_args()
    
    # Handle Threshold
    threshold = args.threshold
    if threshold > 1.0:
        print(f"Warning: Legacy threshold {threshold} detected. Using default 0.5 for CNN.")
        threshold = 0.5
        
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Load Model
    if not args.model_path.exists():
        # Fallback to absolute path or check CWD
        candidates = [
            args.model_path,
            Path("mmr_classifier_best.pth"),
            Path("/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/mmr_classifier_best.pth")
        ]
        found = False
        for p in candidates:
            if p.exists():
                args.model_path = p
                found = True
                break
        if not found:
            print(f"Error: Model not found. Searched: {candidates}")
            sys.exit(1)
            
    model = load_model(args.model_path, device)
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
                
                if prob > threshold:
                    # Candidate for Multi-measure Rest
                    
                    # 2. RUN OCR
                    # Use slightly larger margin for OCR? 
                    # Use existing Logic: vertical margin = 80? Or just use the same crop?
                    # The heuristics used roi_y1_ocr = y1 - 80.
                    # Let's stick to the crop logic but maybe expand vertical context for OCR if number is high up.
                    # But the training crop (margin 20) might be tight for numbers.
                    # Wait, MMR numbers are usually CENTERED or slightly above.
                    # Let's use a larger vertical crop for OCR specifically.
                    
                    ocr_margin_y = 80
                    ox1 = max(0, x1 - 10)
                    ox2 = min(w_img, x2 + 10)
                    oy1 = max(0, y1 - ocr_margin_y)
                    oy2 = min(h_img, y2 + 10)
                    
                    ocr_crop = image[oy1:oy2, ox1:ox2]
                    proc_img = preprocess_image_ocr(ocr_crop)
                    
                    ocr_result, _ = ocr_engine(proc_img)
                    
                    # Filter OCR results (Centering etc)
                    # We can reuse the filter logic from old script or simplify it.
                    # Since CNN is high precision, maybe we can trust OCR more?
                    # But OCR still reads "pizz" etc.
                    
                    found_number = None
                    if ocr_result:
                        roi_w = proc_img.shape[1]
                        center_x = roi_w / 2
                        texts = []
                        for res in ocr_result:
                            # text, score
                            txt = res[1]
                            score = res[2]
                            box = res[0]
                            
                            # Center check
                            xs = [p[0] for p in box]
                            text_cx = sum(xs)/len(xs)
                            if abs(text_cx - center_x) > (roi_w * 0.25): # Relaxed centering
                                continue
                            
                            if score > 0.6:
                                texts.append(txt)
                        
                        full_txt = " ".join(texts)
                        found_number = extract_number_from_text(full_txt)
                    
                    if found_number:
                        print(f"  [FOUND] P{page_num} S{sys_idx} M{m_num}: Prob={prob:.2f} -> OCR={found_number}")
                        overrides.append({
                            "page": page_num - 1,
                            "system": sys_idx,
                            "measure": m_idx,
                            "skip": found_number - 1,
                            "comment": f"CNN-detected ({prob:.2f}): {found_number}"
                        })
                        draw_debug_info(debug_img, x1, y1, x2, y2, 'found', f"R{found_number}", f"{prob:.2f}")
                    else:
                        print(f"  [CHECK] P{page_num} S{sys_idx} M{m_num}: Prob={prob:.2f} -> No OCR Number")
                        draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', f"CNN-only", f"{prob:.2f}")
                        
                else:
                    # Normal measure
                    pass

    # Save
    with open(args.output_overrides, 'w') as f:
        json.dump({"measure_overrides": overrides}, f, indent=2)
        
    if debug_img is not None and args.debug_image:
        cv2.imwrite(str(args.debug_image), debug_img)

if __name__ == "__main__":
    main()
