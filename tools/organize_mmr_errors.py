import json
import cv2
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
from pathlib import Path
import re
from rapidocr_onnxruntime import RapidOCR
import numpy as np
import shutil

# --- Core Logic (Reused) ---
def load_model(model_path, device):
    model = models.resnet18(pretrained=False)
    model.fc = nn.Linear(model.fc.in_features, 1)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device).eval()
    return model

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def predict_crop(model, cv2_img, device):
    if cv2_img is None or cv2_img.size == 0: return 0.0
    img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    input_tensor = transform(pil_img).unsqueeze(0).to(device)
    with torch.no_grad():
        output = model(input_tensor)
        prob = torch.sigmoid(output).item()
    return prob

def map_global_index_to_coords(numbering_data):
    mapping = []
    if "pages" in numbering_data:
        page = numbering_data["pages"][0]
        for s_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                mapping.append({"s": s_idx, "m": m_idx, "bbox": measure["bbox"]})
    return mapping

def organize_errors(eval_root, overrides_root, model_path, device):
    model = load_model(model_path, device)
    ocr_engine = RapidOCR()
    
    base_dir = overrides_root / "categorized_errors"
    if base_dir.exists(): shutil.rmtree(base_dir)
    base_dir.mkdir(exist_ok=True)
    
    stage1_dir = base_dir / "stage1_classifier_errors"
    stage2_dir = base_dir / "stage2_ocr_errors"
    stage1_dir.mkdir(exist_ok=True)
    stage2_dir.mkdir(exist_ok=True)
    
    processed_pages = sorted(list(overrides_root.glob("prokofiev5/page_*")))
    
    s1_items = []
    s2_items = []

    for page_dir in processed_pages:
        page_name = page_dir.name
        work_name = page_dir.parent.name
        
        pred_path = page_dir / "overrides.json"
        numb_path = page_dir / "numbering_initial.json"
        gt_path = eval_root / work_name / page_name / "rest_gt.json"
        img_path = Path(f"data/evaluation2/images/{work_name}/{page_name}.png")
        
        if not gt_path.exists(): continue
            
        gt_data = json.load(open(gt_path)).get("overrides", [])
        pred_data = json.load(open(pred_path)).get("measure_overrides", [])
        numb_data = json.load(open(numb_path))
        img = cv2.imread(str(img_path))
        
        global_map = map_global_index_to_coords(numb_data)
        gt_set = {item['measure_index']: item['rest_count'] for item in gt_data if item['rest_count'] >= 2}
        pred_map = {(item['system'], item['measure']): item['skip'] + 1 for item in pred_data}
            
        # Robust Shift Search
        best_shift = 0
        max_tps = 0
        for s in [-2, -1, 0, 1, 2]:
            tps = 0
            for g_idx in gt_set.keys():
                target = g_idx + s
                if 0 <= target < len(global_map):
                    key = (global_map[target]['s'], global_map[target]['m'])
                    if key in pred_map: tps += 1
            if tps > max_tps:
                max_tps = tps
                best_shift = s

        matched_preds = set()
        
        # Helper to get info
        def get_m_info(g_idx, s_val):
            target = g_idx + s_val
            if 0 <= target < len(global_map):
                return global_map[target]
            return None

        # Analyze GTs
        for g_idx, gt_count in gt_set.items():
            m_info = get_m_info(g_idx, best_shift)
            if not m_info: continue
            
            key = (m_info['s'], m_info['m'])
            bbox = m_info['bbox']
            x1, y1, x2, y2 = bbox
            
            # Classifier Prob
            c_crop = img[max(0, y1-20):min(img.shape[0], y2+20), max(0, x1-20):min(img.shape[1], x2+20)]
            prob = predict_crop(model, c_crop, device)
            
            # OCR Analysis
            o_crop_raw = img[max(0, y1-80):min(img.shape[0], y2+20), max(0, x1-20):min(img.shape[1], x2+20)]
            gray = cv2.cvtColor(o_crop_raw, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            proc_ocr = cv2.bitwise_not(binary)
            proc_ocr = cv2.copyMakeBorder(proc_ocr, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            ocr_res, _ = ocr_engine(proc_ocr)
            ocr_raw_txt = ", ".join([res[1] for res in ocr_res]) if ocr_res else "None"

            if key in pred_map:
                matched_preds.add(key)
                pred_count = pred_map[key]
                if pred_count != gt_count:
                    # Stage 2 Error: Mismatch
                    img_name = f"mismatch_{page_name}_s{key[0]}_m{key[1]}.jpg"
                    o_vis = o_crop_raw.copy()
                    cv2.putText(o_vis, f"GT:{gt_count} PRED:{pred_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    cv2.putText(o_vis, f"OCR:{ocr_raw_txt}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                    cv2.imwrite(str(stage2_dir / img_name), o_vis)
                    s2_items.append({"Page": page_name, "Loc": f"S{key[0]}M{key[1]}", "Type": "Mismatch", "GT": gt_count, "Pred": pred_count, "OCR": ocr_raw_txt, "Img": img_name})
            else:
                # FN
                if prob < 0.5:
                    # Stage 1 Error: Classifier Miss
                    img_name = f"fn_s1_{page_name}_s{key[0]}_m{key[1]}.jpg"
                    c_vis = cv2.resize(c_crop, (448, 448)) # clarify
                    cv2.putText(c_vis, f"Prob:{prob:.3f} (Lower than 0.5)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imwrite(str(stage1_dir / img_name), c_vis)
                    s1_items.append({"Page": page_name, "Loc": f"S{key[0]}M{key[1]}", "Type": "FN (Miss)", "Prob": f"{prob:.3f}", "Img": img_name})
                else:
                    # Stage 2 Error: OCR failed to read
                    img_name = f"fn_s2_{page_name}_s{key[0]}_m{key[1]}.jpg"
                    o_vis = o_crop_raw.copy()
                    cv2.putText(o_vis, f"Prob:{prob:.3f} GT:{gt_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    cv2.putText(o_vis, f"OCR:{ocr_raw_txt} (No number found)", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                    cv2.imwrite(str(stage2_dir / img_name), o_vis)
                    s2_items.append({"Page": page_name, "Loc": f"S{key[0]}M{key[1]}", "Type": "FN (No Number)", "GT": gt_count, "Pred": "-", "OCR": ocr_raw_txt, "Img": img_name})

        # Analyze FPs
        for key, pred_count in pred_map.items():
            if key not in matched_preds:
                # Identify Stage (Prob)
                m_info_fp = None
                for m in global_map:
                    if m['s'] == key[0] and m['m'] == key[1]:
                        m_info_fp = m; break
                if not m_info_fp: continue
                
                bbox = m_info_fp['bbox']
                x1, y1, x2, y2 = bbox
                c_crop_fp = img[max(0, y1-20):min(img.shape[0], y2+20), max(0, x1-20):min(img.shape[1], x2+20)]
                prob_fp = predict_crop(model, c_crop_fp, device)
                
                # FP is almost always Stage 1 Hallucination if prob is high
                img_name = f"fp_s1_{page_name}_s{key[0]}_m{key[1]}.jpg"
                c_vis = cv2.resize(c_crop_fp, (448, 448))
                cv2.putText(c_vis, f"Prob:{prob_fp:.3f} Hallucination", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.imwrite(str(stage1_dir / img_name), c_vis)
                s1_items.append({"Page": page_name, "Loc": f"S{key[0]}M{key[1]}", "Type": "FP (Hallucination)", "Prob": f"{prob_fp:.3f}", "Img": img_name})

    # Create Summary Reports in Each Dir
    with open(stage1_dir / "SUMMARY.md", "w") as f:
        f.write("# Stage 1 (Classifier) Errors\n\n")
        f.write("| Page | Loc | Type | Prob | Image |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for it in s1_items:
            f.write(f"| {it['Page']} | {it['Loc']} | {it['Type']} | {it['Prob']} | ![]({it['Img']}) |\n")

    with open(stage2_dir / "SUMMARY.md", "w") as f:
        f.write("# Stage 2 (OCR) Errors\n\n")
        f.write("| Page | Loc | Type | GT | Pred | OCR Result | Image |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for it in s2_items:
            f.write(f"| {it['Page']} | {it['Loc']} | {it['Type']} | {it['GT']} | {it['Pred']} | {it['OCR']} | ![]({it['Img']}) |\n")

    print(f"Organized analysis complete. See {base_dir}")

if __name__ == "__main__":
    analyze_all_processed = organize_errors
    analyze_all_processed(
        Path("data/evaluation2/rest_gt"),
        Path("logs/experiments/batch_cnnv1"),
        Path("mmr_classifier_best.pth"),
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
    )
