import json
from pathlib import Path
import sys

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

def find_failures(scored_path, gt_path, threshold=0.1):
    with open(gt_path, "r") as f:
        gt_data = json.load(f)
        gt_boxes = [tuple(b["barline_location"]) for b in gt_data if "barline_location" in b]
    
    with open(scored_path, "r") as f:
        preds_all = json.load(f)
        preds = [p for p in preds_all if p["score"] >= threshold]
        pred_boxes = [tuple(p["bbox"]) for p in preds]

    res = greedy_barline_match(pred_boxes, gt_boxes, rule_name="center_anchor")
    
    # 1. Get exact FN bbox
    fn_list = []
    for fn_idx in res.false_negative_indices:
        fn_list.append(gt_boxes[fn_idx])
        
    # 2. Get exact FP bbox and score
    fp_list = []
    for fp_idx in res.false_positive_indices:
        bbox = pred_boxes[fp_idx]
        score = next(p["score"] for p in preds if tuple(p["bbox"]) == bbox)
        fp_list.append((bbox, score))
        
    return fn_list, fp_list

def main():
    targets = [
        ("Sibelius-Violin_Concerto-Viola", "page_004"),
        ("Shostakovich-Sym5-Va", "page_003"),
        ("Va_Prokofiev_Symphony1", "page_005")
    ]
    
    gt_root = Path("data/evaluation2/annotations")
    scored_root = Path("logs/issue53_full_eval_rescue_v1")
    
    print("Failure Identification for Iter 6:")
    for score, page in targets:
        gt_file = sorted(list((gt_root / score / page).glob("boxes_sorted*.json")), reverse=True)[0]
        scored_file = scored_root / f"eval2_{score}_{page}" / "pipeline2_no_peak_scored.json"
        
        fns, fps = find_failures(scored_file, gt_file)
        print(f"\nPage: {score}/{page}")
        for fn in fns:
            print(f"  FN: {fn}")
        for fp_bbox, fp_score in fps:
            print(f"  FP: {fp_bbox} (Score: {fp_score:.4f})")

if __name__ == "__main__":
    main()
