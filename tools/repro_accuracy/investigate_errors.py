import json
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent))
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

def investigate_run(dataset_name, run_path):
    # Depending on the stage, we might look at hybrid_results or probe_scan
    # For Issue 117 verification, the final results are in intermediate/probe_scan
    # wait, the manifest says where the results are.
    
    scored_dir = run_path / "intermediate/probe_scan"
    gt_base = Path(f"data/evaluation2/annotations/{dataset_name}")
    
    total_tp, total_fp, total_fn = 0, 0, 0
    
    print(f"Investigating {dataset_name} in {run_path}")
    print("-" * 40)
    
    print(f"Scanning {scored_dir}...")
    for scored_file in sorted(scored_dir.rglob("pipeline2_no_peak_scored.json")):
        # print(f"Processing candidate: {scored_file}")
        parts = scored_file.parent.name.split("_")
        page_name = parts[-2] + "_" + parts[-1]
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists(): 
            # print(f"  GT file not found: {gt_file}")
            continue
        
        data = load_json(scored_file)
        # Store original objects to correctly retrieve scores later
        filtered_candidates = [c for c in data if c["score"] >= 0.4]
        preds = [tuple(c["bbox"]) for c in filtered_candidates]
        gts = get_gt_boxes(load_json(gt_file))
        
        # Use the same matching parameters as verify_pipeline_accuracy.py
        res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0)
        
        if len(res.false_positive_indices) > 0 or len(res.false_negative_indices) > 0:
            print(f"Page: {page_name} | TP: {len(res.matches)}, FP: {len(res.false_positive_indices)}, FN: {len(res.false_negative_indices)}")
            if len(res.false_positive_indices) > 0:
                print("  FPs:")
                for idx in res.false_positive_indices:
                    cand = filtered_candidates[idx]
                    print(f"    {preds[idx]} (Score: {cand['score']:.3f})")
            if len(res.false_negative_indices) > 0:
                print("  FNs:")
                for idx in res.false_negative_indices:
                    print(f"    {gts[idx]}")
            print("-" * 20)
            
        total_tp += len(res.matches)
        total_fp += len(res.false_positive_indices)
        total_fn += len(res.false_negative_indices)
        
    print(f"\nFinal Totals for {dataset_name}:")
    print(f"TP: {total_tp}, FP: {total_fp}, FN: {total_fn}")
    print(f"Recall: {total_tp/(total_tp+total_fn):.1%}, Precision: {total_tp/(total_tp+total_fp):.1%}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=str, required=True)
    args = parser.parse_args()
    
    run_path = Path(args.run_dir)
    manifest = load_json(run_path / "manifest.json")
    pdf_name = Path(manifest["config"]["inputs"]["pdf_path"]).stem
    investigate_run(pdf_name, run_path)

if __name__ == "__main__":
    main()
