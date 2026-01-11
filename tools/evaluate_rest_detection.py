import argparse
import json
import os
import sys
from pathlib import Path
import pandas as pd
from collections import defaultdict

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def map_global_index_to_coords(numbering_data):
    """
    Returns a list mapping global_index -> (system_idx, measure_idx)
    """
    mapping = []
    if "pages" in numbering_data:
        # Assuming single page per file in this batch context
        page = numbering_data["pages"][0]
        for s_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                mapping.append((s_idx, m_idx))
    return mapping

def evaluate_rest_detection(eval_root, overrides_root):
    """
    Evaluates Multi-measure Rest detection performance.
    """
    
    results = []
    
    # Iterate over Ground Truth files
    gt_files = sorted(list(eval_root.glob("**/rest_gt.json")))
    
    total_tp = 0
    total_fp = 0
    total_fn = 0
    
    for gt_path in gt_files:
        # Determine work and page from path
        # Expected: .../rest_gt/<work>/<page>/rest_gt.json
        parts = gt_path.parts
        page_name = parts[-2]
        work_name = parts[-3]
        
        # Load GT
        try:
            gt_data = load_json(gt_path)
            gt_items = gt_data.get("overrides", []) # List of {measure_index, rest_count}
        except Exception as e:
            print(f"Error loading GT {gt_path}: {e}")
            continue

        # Load Definitions (Predictions)
        # Expected: .../<work>/<page>/overrides.json
        page_dir = overrides_root / work_name / page_name
        pred_path = page_dir / "overrides.json"
        numbering_path = page_dir / "numbering_initial.json"
        
        if not pred_path.exists() or not numbering_path.exists():
            print(f"Prediction or Numbering not found for {work_name}/{page_name}")
            # All GTs are FNs
            fn = len(gt_items)
            results.append({
                "Work": work_name,
                "Page": page_name,
                "TP": 0,
                "FP": 0,
                "FN": fn
            })
            total_fn += fn
            continue
            
        try:
            pred_data = load_json(pred_path)
            pred_overrides = pred_data.get("measure_overrides", []) # {system, measure, skip}
            
            numbering_data = load_json(numbering_path)
            global_map = map_global_index_to_coords(numbering_data)
        except Exception as e:
            print(f"Error loading Pred/Numbering {pred_path}: {e}")
            continue
            
        # Build GT Map: (system, measure) -> skip
        gt_map = {}
        valid_gt = True
        for item in gt_items:
            g_idx = item['measure_index']
            count = item['rest_count']
            if count < 2: continue # Ignore 1-bar rests (not MMR)
            
            if g_idx >= len(global_map):
                print(f"Warning: GT index {g_idx} out of bounds for {work_name}/{page_name}")
                valid_gt = False
                break
                
            s_idx, m_idx = global_map[g_idx]
            gt_map[(s_idx, m_idx)] = count - 1 # skip = count - 1
            
        if not valid_gt:
            continue
            
        # Build Pred Map: (system, measure) -> skip
        pred_map = {}
        for item in pred_overrides:
            key = (item['system'], item['measure'])
            pred_map[key] = item['skip']
            
        tp = 0
        fp = 0
        fn = 0
        
        # Check TPs and FNs (Iterate GT)
        # Match requirement: Location matches AND skip count matches (exact)
        for key, skip_val in gt_map.items():
            if key in pred_map:
                if pred_map[key] == skip_val:
                    tp += 1
                else:
                    # Location match but Count mismatch
                    # Penalize as missed the correct one => FN
                    # And predicted a wrong one => FP
                    fn += 1 
                    fp += 1
                    # print(f"Mismatch {work_name}/{page_name} {key}: GT={skip_val} Pred={pred_map[key]}")
            else:
                fn += 1
                # print(f"Missed {work_name}/{page_name} {key}")
                
        # Check FPs (Iterate Preds not in GT)
        for key, skip_val in pred_map.items():
            if key not in gt_map:
                fp += 1
                # print(f"False Positive {work_name}/{page_name} {key}")
                
        results.append({
            "Work": work_name,
            "Page": page_name,
            "TP": tp,
            "FP": fp,
            "FN": fn
        })
        
        total_tp += tp
        total_fp += fp
        total_fn += fn

    df = pd.DataFrame(results)
    
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print("\n--- Evaluation Results ---")
    try:
        print(df.to_markdown(index=False))
    except:
        print(df.to_string(index=False))
        
    print("\n--- Summary ---")
    print(f"Total Pages: {len(results)}")
    print(f"Total GT Rests: {total_tp + total_fn}")
    print(f"True Positives: {total_tp}")
    print(f"False Positives: {total_fp}")
    print(f"False Negatives: {total_fn}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    
    # Save results
    output_res_csv = overrides_root / "mmr_evaluation_results.csv"
    df.to_csv(output_res_csv, index=False)
    
    summary_md = overrides_root / "mmr_evaluation_summary.md"
    with open(summary_md, "w") as f:
        f.write("# Multi-measure Rest Detection Evaluation\n\n")
        f.write(f"- Precision: **{precision:.4f}**\n")
        f.write(f"- Recall:    **{recall:.4f}**\n")
        f.write(f"- F1 Score:  **{f1:.4f}**\n\n")
        f.write("## Per Page Details\n")
        try:
            f.write(df.to_markdown(index=False))
        except:
            f.write(df.to_string(index=False))

    print(f"\nSaved report to {summary_md}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True, help="Root of rest_gt data")
    parser.add_argument("--overrides-root", type=Path, required=True, help="Root of prediction outputs")
    args = parser.parse_args()
    
    evaluate_rest_detection(args.eval_root, args.overrides_root)
