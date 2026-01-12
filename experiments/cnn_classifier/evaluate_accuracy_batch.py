
import argparse
import json
from pathlib import Path
from tqdm import tqdm
import csv
from collections import defaultdict

def compute_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    if inter_area <= 0: return 0
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    
    union_area = box1_area + box2_area - inter_area
    if union_area <= 0: return 0
    return inter_area / union_area

def find_gt_file(gt_root, subdir, page_name):
    # Try multiple common naming patterns
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists(): return None
    
    # Priority: newest sorted file
    candidates = list(base_dir.glob("boxes_sorted*.json"))
    if candidates:
        candidates.sort(reverse=True) # Get latest vXXXXX
        return candidates[0]
    
    f = base_dir / "boxes_sorted.json"
    if f.exists(): return f
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", required=True)
    parser.add_argument("--gt-root", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    scored_files = list(Path(args.scored_root).glob("*_scored.json"))
    stats = []

    print(f"Processing {len(scored_files)} scored files...")

    for json_path in tqdm(scored_files):
        run_id = json_path.stem.replace("_scored", "")
        # Naming: eval2_SubdirName_page_XXX
        parts = run_id.split('_')
        try:
            page_idx = -1
            for i, p in enumerate(parts):
                if p == "page":
                    page_idx = i
                    break
            if page_idx == -1: continue
            
            subdir = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])
        except Exception:
            continue

        # Load Scored Candidates
        with open(json_path, 'r') as f:
            candidates = json.load(f)

        # Load GT
        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        gt_boxes = []
        if gt_path:
            with open(gt_path, 'r') as f:
                gt_data = json.load(f)
                for item in gt_data:
                    # Handle both list and dict formats
                    if isinstance(item, list):
                        gt_boxes.append(item[:4])
                    elif isinstance(item, dict):
                        if "box" in item: gt_boxes.append(item["box"])
                        elif "barline_location" in item: gt_boxes.append(item["barline_location"])
        else:
             continue
        
        # Calculate Metrics
        gt_is_matched = [False] * len(gt_boxes)
        gt_has_candidate = [False] * len(gt_boxes)
        
        tp = 0
        fp = 0
        
        accepted_candidates = [c for c in candidates if c["score"] > args.threshold]
        
        # 1. Check TPs and track which GTs were hit by ANY candidate
        for cand in accepted_candidates:
            box = cand["bbox"]
            best_iou = 0
            best_idx = -1
            
            for idx, gt in enumerate(gt_boxes):
                iou = compute_iou(box, gt)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx
            
            if best_iou > 0.5:
                tp += 1
                gt_is_matched[best_idx] = True
            else:
                fp += 1
        
        # 2. Check which GTs had NO candidate at all (Detector Miss)
        for idx, gt in enumerate(gt_boxes):
            for cand in candidates: # Check ALL candidates, not just accepted ones
                if compute_iou(cand["bbox"], gt) > 0.5:
                    gt_has_candidate[idx] = True
                    break
        
        # Final breakdown
        fn_total = len(gt_boxes) - sum(gt_is_matched)
        fn_cnn = 0
        fn_det = 0
        
        for idx in range(len(gt_boxes)):
            if not gt_is_matched[idx]:
                if gt_has_candidate[idx]:
                    fn_cnn += 1
                else:
                    fn_det += 1
        
        stats.append({
            "score": subdir,
            "page": page_name,
            "tp": tp,
            "fp": fp,
            "fn_total": fn_total,
            "fn_cnn": fn_cnn,
            "fn_det": fn_det,
            "gt_count": len(gt_boxes)
        })

    # Output CSV
    with open(args.output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["score", "page", "tp", "fp", "fn_total", "fn_cnn", "fn_det", "gt_count"])
        writer.writeheader()
        writer.writerows(stats)

    # Aggregate
    agg = defaultdict(lambda: {"tp": 0, "fp": 0, "fn_total": 0, "fn_cnn": 0, "fn_det": 0, "gt": 0, "pages": 0})
    for s in stats:
        bucket = agg[s["score"]]
        bucket["tp"] += s["tp"]
        bucket["fp"] += s["fp"]
        bucket["fn_total"] += s["fn_total"]
        bucket["fn_cnn"] += s["fn_cnn"]
        bucket["fn_det"] += s["fn_det"]
        bucket["gt"] += s["gt_count"]
        bucket["pages"] += 1
    
    print("\nCorrected Evaluation Summary (No Peak):")
    print(f"{'Score':<35} | {'Pages':<5} | {'TP':<5} | {'FP':<5} | {'FN(Tot)':<8} | {'FN(CNN)':<8} | {'FN(Det)':<8} | {'Recall':<6} | {'Prec':<6}")
    print("-" * 110)
    for score, data in agg.items():
        tp = data["tp"]
        fp = data["fp"]
        fn = data["fn_total"]
        recall = tp / data["gt"] if data["gt"] > 0 else 0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        print(f"{score:<35} | {data['pages']:<5} | {tp:<5} | {fp:<5} | {fn:<8} | {data['fn_cnn']:<8} | {data['fn_det']:<8} | {recall:.1%} | {prec:.1%}")

if __name__ == "__main__":
    main()
