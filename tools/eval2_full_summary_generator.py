import json
import os
import csv
from pathlib import Path

def get_box(c): 
    if isinstance(c, dict):
        return c.get('box', c.get('bbox', c))
    return c

def evaluate_page(pred_json, gt_json):
    if not os.path.exists(pred_json): return None
    if not os.path.exists(gt_json): return None
    
    with open(pred_json) as f:
        preds = json.load(f)
    with open(gt_json) as f:
        gts = json.load(f)
    
    pred_boxes = [get_box(c) for c in preds]
    # Filter out non-list boxes if any
    pred_boxes = [b for b in pred_boxes if isinstance(b, list) and len(b) == 4]
    
    gt_boxes = [g['barline_location'] for g in gts if 'barline_location' in g]
    
    tp = 0
    matched_gt = set()
    matched_pred = set()
    
    for pi, pb in enumerate(pred_boxes):
        pcx = (pb[0] + pb[2]) / 2.0
        pcy = (pb[1] + pb[3]) / 2.0
        for gi, gb in enumerate(gt_boxes):
            if gi in matched_gt: continue
            gcx = (gb[0] + gb[2]) / 2.0
            gcy = (gb[1] + gb[3]) / 2.0
            # Centroid distance match
            if abs(pcx - gcx) < 15 and abs(pcy - gcy) < 60:
                matched_gt.add(gi)
                matched_pred.add(pi)
                tp += 1
                break
    
    fp = len(pred_boxes) - len(matched_pred)
    fn = len(gt_boxes) - len(matched_gt)
    return tp, fp, fn

scores = [
    "Shostakovich-Festival_Overture_Va",
    "Shostakovich-Sym5-Va",
    "Sibelius-Violin_Concerto-Viola",
    "Va_Prokofiev_Symphony1",
    "Va__Prokofiev_Symphony5"
]

run_root = Path("logs/full_pipeline_runs/issue120_final_v1")
results = []

print(f"{'Score':<35} | {'Page':<8} | TP | FP | FN")
print("-" * 65)

for score in scores:
    score_dir = run_root / score
    if not score_dir.exists(): continue
    
    probe_scan_dir = score_dir / "intermediate" / "probe_scan"
    if not probe_scan_dir.exists(): continue
    
    # We want to iterate through ALL expected pages for this score
    # To be simple, just iterate existing directories
    for page_dir in sorted(probe_scan_dir.iterdir()):
        if not page_dir.is_dir(): continue
        
        # page_dir name is like eval2_Shostakovich-Festival_Overture_Va_page_001
        parts = page_dir.name.split("_")
        page_id = parts[-1]
        if not page_id.startswith("page"):
             # maybe it's the run_id based name
             page_id = parts[-1] # still likely the last
        
        # Try to find page_00X in the name
        import re
        m = re.search(r"page_(\d+)", page_dir.name)
        if m:
            page_id = f"page_{m.group(1)}"
        else:
            continue

        pred_json = page_dir / "pipeline2_no_peak_filtered_cnn.json"
        gt_json = Path(f"data/evaluation2/annotations/{score}/{page_id}/boxes_sorted.json")
        
        eval_res = evaluate_page(str(pred_json), str(gt_json))
        if eval_res:
            tp, fp, fn = eval_res
            results.append({
                "score": score,
                "page": page_id,
                "tp": tp,
                "fp": fp,
                "fn": fn
            })
            print(f"{score:<35} | {page_id:<8} | {tp:2} | {fp:2} | {fn:2}")

# Global totals
total_tp = sum(r['tp'] for r in results)
total_fp = sum(r['fp'] for r in results)
total_fn = sum(r['fn'] for r in results)
print("-" * 65)
print(f"{'TOTAL (' + str(len(results)) + ' pages)':<46} | {total_tp:4} | {total_fp:4} | {total_fn:4}")

# Save to CSV
with open("logs/issue120_final_v1_summary.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["score", "page", "tp", "fp", "fn"])
    writer.writeheader()
    writer.writerows(results)
