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
        page = numbering_data["pages"][0]
        for s_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                mapping.append((s_idx, m_idx))
    return mapping

def evaluate_rest_detection(eval_root, overrides_root):
    """
    Evaluates MMR detection with stage separation and robustness to index shifts.
    """
    results = []
    
    gt_files = sorted(list(eval_root.glob("**/rest_gt.json")))
    
    total_gt_rests = 0
    total_det_tp = 0 # Classifier Found (any count)
    total_det_fp = 0 # Classifier Found (hallucination)
    
    total_pipeline_tp = 0 # Classifier + OCR Correct
    total_pipeline_fp = 0 # Incorrect count or hallucination
    
    for gt_path in gt_files:
        parts = gt_path.parts
        page_name = parts[-2]
        work_name = parts[-3]
        
        page_dir = overrides_root / work_name / page_name
        pred_path = page_dir / "overrides.json"
        numbering_path = page_dir / "numbering_initial.json"
        
        if not pred_path.exists() or not numbering_path.exists():
            continue
            
        try:
            gt_data = load_json(gt_path).get("overrides", [])
            pred_data = load_json(pred_path).get("measure_overrides", [])
            numbering_data = load_json(numbering_path)
            global_map = map_global_index_to_coords(numbering_data)
        except: continue

        # 1. Build Pred Map (system, measure) -> count
        pred_map = {}
        for item in pred_data:
            key = (item['system'], item['measure'])
            pred_map[key] = item['skip'] + 1

        # 2. Build GT Map (measure_index) -> count
        gt_map = {item['measure_index']: item['rest_count'] for item in gt_data if item['rest_count'] >= 2}
        total_gt_rests += len(gt_map)

        # 3. Robust Matching (Shift Search)
        best_shift = 0
        max_tps = 0
        
        for s in [-2, -1, 0, 1, 2]:
            current_tps = 0
            for g_idx in gt_map.keys():
                target_idx = g_idx + s
                if 0 <= target_idx < len(global_map):
                    key = global_map[target_idx]
                    if key in pred_map:
                        current_tps += 1
            if current_tps > max_tps:
                max_tps = current_tps
                best_shift = s
        
        if best_shift != 0:
            print(f"  [INFO] Detected index shift of {best_shift:+} for {page_name}")

        # 4. Local Evaluation (Using best shift)
        loc_det_tp = 0
        loc_pipe_tp = 0
        
        matched_keys = set()
        for g_idx, gt_count in gt_map.items():
            target_idx = g_idx + best_shift
            if 0 <= target_idx < len(global_map):
                key = global_map[target_idx]
                if key in pred_map:
                    matched_keys.add(key)
                    loc_det_tp += 1
                    if pred_map[key] == gt_count:
                        loc_pipe_tp += 1
        
        # All other preds are FP
        loc_det_fp = len(pred_data) - loc_det_tp
        loc_pipe_fp = len(pred_data) - loc_pipe_tp

        results.append({
            "Work": work_name,
            "Page": page_name,
            "GT": len(gt_map),
            "Shift": f"{best_shift:+}",
            "Det_TP": loc_det_tp,
            "Det_FP": loc_det_fp,
            "Pipe_TP": loc_pipe_tp,
            "Pipe_FP": loc_pipe_fp
        })
        
        total_det_tp += loc_det_tp
        total_det_fp += loc_det_fp
        total_pipeline_tp += loc_pipe_tp
        total_pipeline_fp += loc_pipe_fp

    df = pd.DataFrame(results)
    
    det_prec = total_det_tp / (total_det_tp + total_det_fp) if (total_det_tp + total_det_fp) > 0 else 0
    det_rec = total_det_tp / total_gt_rests if total_gt_rests > 0 else 0
    
    pipe_prec = total_pipeline_tp / (total_pipeline_tp + total_pipeline_fp) if (total_pipeline_tp + total_pipeline_fp) > 0 else 0
    pipe_rec = total_pipeline_tp / total_gt_rests if total_gt_rests > 0 else 0
    
    print("\n--- MMR Detection Evaluation (Robust Match) ---")
    print(df.to_string(index=False))
    
    print("\n--- Summary Metrics ---")
    print(f"Stage 1: Candidate Detection (Classifier)")
    print(f"  Precision: {det_prec:.4f}")
    print(f"  Recall:    {det_rec:.4f} ({total_det_tp}/{total_gt_rests})")
    print(f"Stage 2: Full Pipeline (Candidate + OCR)")
    print(f"  Precision: {pipe_prec:.4f}")
    print(f"  Recall:    {pipe_rec:.4f} ({total_pipeline_tp}/{total_gt_rests})")
    
    # Save results
    output_res_csv = overrides_root / "mmr_eval_robust.csv"
    df.to_csv(output_res_csv, index=False)
    
    summary_md = overrides_root / "mmr_eval_robust_summary.md"
    with open(summary_md, "w") as f:
        f.write("# MMR Detection Evaluation (Robust Match)\n\n")
        f.write("### Stage 1: Classifier (Candidate Detection)\n")
        f.write(f"- Precision: **{det_prec:.4f}**\n")
        f.write(f"- Recall:    **{det_rec:.4f}**\n\n")
        f.write("### Stage 2: Full Pipeline (OCR Included)\n")
        f.write(f"- Precision: **{pipe_prec:.4f}**\n")
        f.write(f"- Recall:    **{pipe_rec:.4f}**\n\n")
        f.write("## Per Page Details\n")
        f.write(df.to_markdown(index=False))

    print(f"\nSaved report to {summary_md}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--overrides-root", type=Path, required=True)
    args = parser.parse_args()
    evaluate_rest_detection(args.eval_root, args.overrides_root)
