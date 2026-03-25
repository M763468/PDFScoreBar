import json
import sys
from pathlib import Path

sys.path.append('/home/masaki_muramatsu/ws_PDFScoreBar')
from src.common.barline_evaluation import greedy_barline_match

def load_json(p):
    with open(p, 'r') as f:
        return json.load(f)

def get_gt_boxes(gt_data):
    boxes = []
    for item in gt_data:
        if isinstance(item, list):
            boxes.append(tuple(item[:4]))
        elif isinstance(item, dict):
            if "barline_location" in item:
                boxes.append(tuple(item["barline_location"]))
            elif "box" in item:
                boxes.append(tuple(item["box"]))
    return boxes

def main():
    # Use the latest run where min_ratio=0.50 was applied (20260325_130027)
    scored_dir = Path("logs/full_pipeline_runs/20260325_130027/intermediate/probe_scan")
    gt_base = Path("data/evaluation2/annotations/Shostakovich-Festival_Overture_Va")
    
    tp, fp, fn = 0, 0, 0
    for filtered_file in sorted(scored_dir.rglob("pipeline2_no_peak_filtered_cnn.json")):
        page_name = filtered_file.parent.name.split("_")[-2] + "_" + filtered_file.parent.name.split("_")[-1]
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists(): continue
            
        data = load_json(filtered_file)
        preds = [tuple(c) if isinstance(c, list) else tuple(c["bbox"]) for c in data]
        gts = get_gt_boxes(load_json(gt_file))
        
        # Original rule center_anchor, 12.0px threshold
        res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0)
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)
        
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    print(f"Shostakovich (CNN Filtered FINAL) TP: {tp}, FP: {fp}, FN: {fn}")
    print(f"Recall: {recall:.2%}, Precision: {precision:.2%}")

if __name__ == "__main__":
    main()
