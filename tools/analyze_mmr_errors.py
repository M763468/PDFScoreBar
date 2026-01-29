import json
from pathlib import Path

import cv2
import torch
import torch.nn as nn
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from torchvision import models, transforms


# --- Reuse logic ---
def load_model(model_path, device):
    model = models.resnet18(pretrained=False)
    model.fc = nn.Linear(model.fc.in_features, 1)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device).eval()
    return model


transform = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


def predict_crop(model, cv2_img, device):
    if cv2_img is None or cv2_img.size == 0:
        return 0.0
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


def analyze_all_processed(eval_root, overrides_root, model_path, device):
    model = load_model(model_path, device)
    ocr_engine = RapidOCR()

    output_dir = overrides_root / "comprehensive_analysis_v2"
    output_dir.mkdir(exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Scan all works (depth 2: work/page/overrides.json)
    processed_pages = sorted(list(overrides_root.glob("*/*/overrides.json")))
    processed_pages = [p.parent for p in processed_pages]  # Get page dir

    report_items = []
    summary_data = []

    for page_dir in processed_pages:
        page_name = page_dir.name
        work_name = page_dir.parent.name

        pred_path = page_dir / "overrides.json"
        numb_path = page_dir / "numbering_initial.json"
        gt_path = eval_root / work_name / page_name / "rest_gt.json"
        img_path = Path(f"data/evaluation2/images/{work_name}/{page_name}.png")
        if not img_path.exists():
            # Try alt path for prokofiev1
            if work_name == "Va_Prokofiev_Symphony1":
                img_path = Path(f"data/evaluation2/images/prokofiev1/{page_name}.png")

        if not gt_path.exists():
            continue

        print(f"Analyzing {work_name}/{page_name}...")

        gt_data = json.load(open(gt_path)).get("overrides", [])
        pred_data = json.load(open(pred_path)).get("measure_overrides", [])
        numb_data = json.load(open(numb_path))
        img = cv2.imread(str(img_path))

        if img is None:
            print(f"Error loading image: {img_path}")
            continue

        global_map = map_global_index_to_coords(numb_data)

        gt_set = {
            item["measure_index"]: item["rest_count"] for item in gt_data if item["rest_count"] >= 2
        }
        pred_map = {(item["system"], item["measure"]): item["skip"] + 1 for item in pred_data}

        # Robust Shift Search
        best_shift = 0
        max_tps = 0
        for s in [-2, -1, 0, 1, 2]:
            tps = 0
            for g_idx in gt_set.keys():
                target = g_idx + s
                if 0 <= target < len(global_map):
                    key = (global_map[target]["s"], global_map[target]["m"])
                    if key in pred_map:
                        tps += 1
            if tps > max_tps:
                max_tps = tps
                best_shift = s

        # Results with Shift
        tp_found = 0
        fp_found = 0
        fn_found = 0
        mm_found = 0

        matched_preds = set()

        # Check GTs
        for g_idx, gt_count in gt_set.items():
            target = g_idx + best_shift
            if 0 <= target < len(global_map):
                m_info = global_map[target]
                key = (m_info["s"], m_info["m"])
                bbox = m_info["bbox"]

                # Attributions
                x1, y1, x2, y2 = bbox
                c_crop = img[
                    max(0, y1 - 20) : min(img.shape[0], y2 + 20),
                    max(0, x1 - 20) : min(img.shape[1], x2 + 20),
                ]
                prob = predict_crop(model, c_crop, device)

                if key in pred_map:
                    matched_preds.add(key)
                    pred_count = pred_map[key]
                    if pred_count == gt_count:
                        status = "TP"
                        tp_found += 1
                    else:
                        status = "Mismatch"
                        mm_found += 1

                    report_items.append(
                        {
                            "Work": work_name,
                            "Page": page_name,
                            "Status": status,
                            "Loc": f"S{key[0]} M{key[1]}",
                            "GT": gt_count,
                            "Pred": pred_count,
                            "Prob": f"{prob:.3f}",
                            "Image": f"{work_name}_{status}_{page_name}_s{key[0]}_m{key[1]}.jpg",
                            "Raw": c_crop,
                            "Bbox": bbox,
                            "FullImg": img,
                        }
                    )
                else:
                    status = "FN"
                    fn_found += 1
                    report_items.append(
                        {
                            "Work": work_name,
                            "Page": page_name,
                            "Status": status,
                            "Loc": f"S{key[0]} M{key[1]}",
                            "GT": gt_count,
                            "Pred": "-",
                            "Prob": f"{prob:.3f}",
                            "Image": f"{work_name}_{status}_{page_name}_s{key[0]}_m{key[1]}.jpg",
                            "Raw": c_crop,
                            "Bbox": bbox,
                            "FullImg": img,
                        }
                    )
            else:
                # OOB FN
                fn_found += 1

        # Check FPs
        for key, pred_count in pred_map.items():
            if key not in matched_preds:
                fp_found += 1
                # Find bbox
                bbox = None
                for m in global_map:
                    if m["s"] == key[0] and m["m"] == key[1]:
                        bbox = m["bbox"]
                        break
                if not bbox:
                    continue

                x1, y1, x2, y2 = bbox
                c_crop = img[
                    max(0, y1 - 20) : min(img.shape[0], y2 + 20),
                    max(0, x1 - 20) : min(img.shape[1], x2 + 20),
                ]
                prob = predict_crop(model, c_crop, device)

                status = "FP"
                report_items.append(
                    {
                        "Work": work_name,
                        "Page": page_name,
                        "Status": status,
                        "Loc": f"S{key[0]} M{key[1]}",
                        "GT": "-",
                        "Pred": pred_count,
                        "Prob": f"{prob:.3f}",
                        "Image": f"{work_name}_{status}_{page_name}_s{key[0]}_m{key[1]}.jpg",
                        "Raw": c_crop,
                        "Bbox": bbox,
                        "FullImg": img,
                    }
                )

        summary_data.append(
            {
                "Work": work_name,
                "Page": page_name,
                "Shift": f"{best_shift:+}",
                "TP": tp_found,
                "FP": fp_found,
                "FN": fn_found,
                "MM": mm_found,
            }
        )

    # Save Images and Write Report
    with open(output_dir / "investigation_v2.md", "w") as f:
        f.write("# MMR Investigation Report V2 (Robust index matching)\n\n")
        f.write(
            "Detected and corrected per-page index shifts. Decoupled Classifier (Prob) and OCR (Pred) results.\n\n"
        )

        f.write("## 1. Summary\n")
        f.write("| Work | Page | Shift | TP | FP | FN | Mismatch |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for s in summary_data:
            f.write(
                f"| {s['Work']} | {s['Page']} | {s['Shift']} | {s['TP']} | {s['FP']} | {s['FN']} | {s['MM']} |\n"
            )

        f.write("\n## 2. Details\n")
        f.write("| Work | Page | Status | Loc | GT | Pred | Prob | OCR Raw | Image |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

        for item in sorted(report_items, key=lambda x: (x["Work"], x["Page"], x["Loc"])):
            # OCR stage analysis
            o_crop = item["FullImg"][
                max(0, item["Bbox"][1] - 80) : min(item["FullImg"].shape[0], item["Bbox"][3] + 20),
                max(0, item["Bbox"][0] - 20) : min(item["FullImg"].shape[1], item["Bbox"][2] + 20),
            ]
            # Predict raw text for report
            gray = cv2.cvtColor(o_crop, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            proc_ocr = cv2.bitwise_not(binary)
            proc_ocr = cv2.copyMakeBorder(proc_ocr, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            ocr_res, _ = ocr_engine(proc_ocr)
            ocr_raw = ", ".join([res[1] for res in ocr_res]) if ocr_res else "None"

            cv2.imwrite(str(images_dir / item["Image"]), o_crop)

            st = item["Status"]
            if st != "TP":
                st = f"**{st}**"

            f.write(
                f"| {item['Work']} | {item['Page']} | {st} | {item['Loc']} | {item['GT']} | {item['Pred']} | {item['Prob']} | {ocr_raw} | ![]({images_dir.name}/{item['Image']}) |\n"
            )

    print(f"Report generated: {output_dir / 'investigation_v2.md'}")


if __name__ == "__main__":
    analyze_all_processed(
        Path("data/evaluation2/rest_gt"),
        Path("logs/experiments/2026-01-12_MMR_Global_Eval_v6_Polish"),
        Path("tools/mmr_training/models/mmr_classifier_best.pth"),
        torch.device("cuda" if torch.cuda.is_available() else "cpu"),
    )
