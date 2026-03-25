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
    det_file = Path("logs/hybrid_generalization/repro_shostakovich_100/20260324_153852/hybrid_results/page_001_hybrid.json")
    gt_file = Path("data/evaluation2/annotations/Shostakovich-Festival_Overture_Va/page_001/boxes_sorted.json")
    
    preds = [tuple(b) for b in load_json(det_file)]
    gts = get_gt_boxes(load_json(gt_file))
    
    res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=15.0)
    print(f"TP: {len(res.matches)}, FP: {len(res.false_positive_indices)}, FN: {len(res.false_negative_indices)}")
    
    print("\nFPs (Predictions not matched to any GT):")
    for idx in res.false_positive_indices:
        print(f"  FP: {preds[idx]}")
        
    print("\nFNs (GTs not matched to any Pred):")
    for idx in res.false_negative_indices:
        print(f"  FN: {gts[idx]}")

if __name__ == "__main__":
    main()
