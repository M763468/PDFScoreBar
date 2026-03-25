import json
import sys
from pathlib import Path
from collections import defaultdict

# Add repo root to sys path to import match logic
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
    # Use localized /tmp data or full repo roots
    hybrid_root = Path("/home/masaki_muramatsu/ws_PDFScoreBar/logs/hybrid_generalization/verify_fixed_v10")
    gt_base = Path("/home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/annotations")

    datasets = [
        "Shostakovich-Festival_Overture_Va",
        "Shostakovich-Sym5-Va",
        "Sibelius-Violin_Concerto-Viola",
        "Va_Prokofiev_Symphony1",
        "Va__Prokofiev_Symphony5"
    ]

    print(f"{'Dataset':<35} | {'GT':<5} | {'TP':<5} | {'FP':<5} | {'FN':<5} | {'Recall':<8}")
    print("-" * 75)

    global_tp, global_fp, global_fn = 0, 0, 0

    for ds in datasets:
        # Find latest results for this dataset
        ds_dirs = list(hybrid_root.glob(f"{ds}/*"))
        if not ds_dirs: continue
        latest_ts = sorted(ds_dirs)[-1]
        hybrid_dir = latest_ts / "hybrid_results"
        gt_root = gt_base / ds
        
        tp, fp, fn = 0, 0, 0
        for json_file in sorted(hybrid_dir.glob("page_*_hybrid.json")):
            page_name = json_file.stem.replace("_hybrid", "")
            gt_file = gt_root / page_name / "boxes_sorted.json"
            if not gt_file.exists(): continue
                
            preds = [tuple(b) for b in load_json(json_file)]
            gts = get_gt_boxes(load_json(gt_file))
            
            res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0)
            tp += len(res.matches)
            fp += len(res.false_positive_indices)
            fn += len(res.false_negative_indices)
            
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        print(f"{ds:<35} | {tp+fn:<5} | {tp:<5} | {fp:<5} | {fn:<5} | {recall:.1%}")
        
        global_tp += tp
        global_fp += fp
        global_fn += fn

    global_recall = global_tp / (global_tp + global_fn) if (global_tp + global_fn) > 0 else 0
    print("-" * 75)
    print(f"{'GLOBAL TOTAL':<35} | {global_tp+global_fn:<5} | {global_tp:<5} | {global_fp:<5} | {global_fn:<5} | {global_recall:.1%}")

if __name__ == "__main__":
    main()
