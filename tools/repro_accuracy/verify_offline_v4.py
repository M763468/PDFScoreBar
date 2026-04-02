import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.common.barline_evaluation import greedy_barline_match

def load_json(p):
    with open(p, 'r') as f:
        return json.load(f)

def get_gt_boxes(gt_data):
    return [tuple(item["barline_location"]) for item in gt_data if "barline_location" in item]

def main():
    scored_dir = Path("logs/full_pipeline_runs/verify_v10_prokofiev5_filtered_v4/intermediate/probe_scan")
    gt_base = Path("data/evaluation2/annotations/Va__Prokofiev_Symphony5")
    tp, fp, fn = 0, 0, 0
    for scored_file in sorted(scored_dir.rglob("pipeline2_no_peak_scored.json")):
        stem = scored_file.parent.name
        # stem format: eval2_Va__Prokofiev_Symphony5_page_011
        parts = stem.split("_")
        page_name = f"{parts[-2]}_{parts[-1]}" # page_011
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists():
            continue
        data = load_json(scored_file)
        preds = [tuple(c["bbox"]) for c in data if c["score"] >= 0.4]
        gts = get_gt_boxes(load_json(gt_file))
        res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0)
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)
        
    print("-" * 50)
    print(f"TOTAL: TP: {tp} | FP: {fp} | FN: {fn}")
    if (tp + fn) > 0:
        print(f"Recall: {tp/(tp+fn):.1%}")
    if (tp + fp) > 0:
        print(f"Precision: {tp/(tp+fp):.1%}")

if __name__ == '__main__':
    main()
