import json
import os
from pathlib import Path

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def get_box_center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

def is_same_fp(box1, box2, tolerance=5):
    c1 = get_box_center(box1)
    c2 = get_box_center(box2)
    return abs(c1[0] - c2[0]) < tolerance and abs(c1[1] - c2[1]) < tolerance

def analyze_fps():
    # Paths
    new_run_dir = Path("/home/masaki_muramatsu/ws_PDFScoreBar/logs/eval_2025_11_29_1764397202")
    old_run_dir = Path("/home/masaki_muramatsu/ws_PDFScoreBar/logs/homr_eval/20251116T220339JST_fn_guard_page3")
    
    # Load New Run Data
    new_metrics = load_json(new_run_dir / "metrics.json")
    new_detections_raw = load_json(new_run_dir / "page_3/page_3_detections.json")
    print("New Detections Type:", type(new_detections_raw))
    if isinstance(new_detections_raw, list):
        print("New Detections Len:", len(new_detections_raw))
        if len(new_detections_raw) > 0:
            print("New Detections[0] Type:", type(new_detections_raw[0]))
    elif isinstance(new_detections_raw, dict):
        print("New Detections Keys:", new_detections_raw.keys())
        
    # Assuming it might be a dict with "boxes" or similar, or a list where the first item is metadata?
    # For now, let's just assign it to new_detections if it's a list, or handle it if dict
    if isinstance(new_detections_raw, list):
        new_detections = new_detections_raw
    else:
        # Try to find the list
        if "predictions" in new_detections_raw:
            new_detections = new_detections_raw["predictions"]
        elif "boxes" in new_detections_raw:
            new_detections = new_detections_raw["boxes"]
        else:
            new_detections = []

    # Load Old Run Data
    old_metrics = load_json(old_run_dir / "metrics.json")
    old_detections_raw = load_json(old_run_dir / "page_3/page_3_detections.json")
    if isinstance(old_detections_raw, list):
        old_detections = old_detections_raw
    else:
        if "predictions" in old_detections_raw:
            old_detections = old_detections_raw["predictions"]
        elif "boxes" in old_detections_raw:
            old_detections = old_detections_raw["boxes"]
        else:
            old_detections = []
    
    # Inspect images structure
    # print("Images type:", type(new_metrics["images"]))
    # print("Images content sample:", new_metrics["images"][0].keys() if isinstance(new_metrics["images"], list) and len(new_metrics["images"]) > 0 else "Not a list or empty")

    def get_fp_indices(metrics_image, num_detections):
        if "matches" not in metrics_image:
            return []
        
        matches = metrics_image["matches"]
        soft_matches = metrics_image.get("soft_matches", [])
        
        print(f"Num Detections: {num_detections}")
        print(f"Num Matches: {len(matches)}")
        print(f"Num Soft Matches: {len(soft_matches)}")
        
        matched_indices = {m["pred_index"] for m in matches}
        soft_indices = {m["pred_index"] for m in soft_matches}
        
        all_indices = set(range(num_detections))
        fp_indices = list(all_indices - matched_indices - soft_indices)
        fp_indices.sort()
        return fp_indices

    if isinstance(new_metrics["images"], list) and len(new_metrics["images"]) > 0:
        img_metrics = new_metrics["images"][0]
        new_fp_indices = get_fp_indices(img_metrics, len(new_detections))
    else:
        new_fp_indices = []

    if isinstance(old_metrics["images"], list) and len(old_metrics["images"]) > 0:
        img_metrics = old_metrics["images"][0]
        old_fp_indices = get_fp_indices(img_metrics, len(old_detections))
    else:
        old_fp_indices = []
    
    new_fp_boxes = [new_detections[i] for i in new_fp_indices]
    old_fp_boxes = [old_detections[i] for i in old_fp_indices]
    
    print(f"New Run FPs: {len(new_fp_indices)}")
    print(f"Old Run FPs: {len(old_fp_indices)}")
    
    # Identify New FPs
    truly_new_fps = []
    existing_fps = []
    
    if len(new_detections) > 0:
        print("First detection item:", new_detections[0])

    def get_box_from_item(item):
        if isinstance(item, list) or isinstance(item, tuple):
            return item
        elif isinstance(item, dict):
            if "orig_bbox" in item:
                return item["orig_bbox"]
            elif "pred_bbox" in item:
                return item["pred_bbox"]
            elif "bbox" in item:
                return item["bbox"]
            elif "box" in item:
                return item["box"]
        return item # Fallback

    for i, item in zip(new_fp_indices, new_fp_boxes):
        box = get_box_from_item(item)
        match_found = False
        for old_item in old_fp_boxes:
            old_box = get_box_from_item(old_item)
            if is_same_fp(box, old_box):
                match_found = True
                break
        
        fp_info = {
            "index": i,
            "box": box,
            "center": get_box_center(box),
            "width": box[2] - box[0],
            "height": box[3] - box[1]
        }
        
        if not match_found:
            truly_new_fps.append(fp_info)
        else:
            existing_fps.append(fp_info)
            
    print("\n=== Newly Introduced FPs (2025-11-29) ===")
    for fp in truly_new_fps:
        print(f"Index: {fp['index']}, Box: {fp['box']}, W: {fp['width']}, H: {fp['height']}, Center: {fp['center']}")
        
    print("\n=== Existing/Recurring FPs (Sample) ===")
    for fp in existing_fps[:5]:
        print(f"Index: {fp['index']}, Box: {fp['box']}, W: {fp['width']}, H: {fp['height']}, Center: {fp['center']}")
        
    # Classification Helper (Simple Heuristics)
    print("\n=== FP Classification Analysis ===")
    
    def classify(fp):
        w, h = fp['width'], fp['height']
        cx, cy = fp['center']
        
        if h < 10: return "Tiny Speck"
        if w > 10: return "Wide Object (Beam/Slur?)"
        if 18 <= h <= 24 and w <= 4: return "Thin Barline Candidate (Potential Stem/Repeat)"
        return "Other Vertical Fragment"

    print("New FPs Classification:")
    for fp in truly_new_fps:
        print(f"  Index {fp['index']}: {classify(fp)}")

    print("Existing FPs Classification Summary:")
    categories = {}
    for fp in existing_fps:
        cat = classify(fp)
        categories[cat] = categories.get(cat, 0) + 1
    
    for cat, count in categories.items():
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    analyze_fps()
