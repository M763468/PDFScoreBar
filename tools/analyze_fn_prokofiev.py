import json
import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes
from src.common.barline_evaluation import greedy_barline_match, is_barline_match


def main():
    # 1. Setup paths
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )
    run_dir = (
        PROJECT_ROOT
        / "logs/full_pipeline_runs/bypass_sr_test/eval2_bypass_sr_test_v2/intermediate/probe_scan/eval2_images_page_001"
    )

    candidates_path = run_dir / "pipeline2_no_peak_candidates.json"
    scored_path = run_dir / "pipeline2_no_peak_scored.json"
    filtered_path = run_dir / "pipeline2_no_peak_filtered_cnn.json"

    # 2. Load data
    gt_boxes = load_ground_truth_boxes(gt_path)
    with open(candidates_path) as f:
        candidates = [tuple(b) for b in json.load(f)]
    with open(scored_path) as f:
        scored_data = json.load(f)
    with open(filtered_path) as f:
        filtered = [tuple(b) for b in json.load(f)]

    # 3. Find Global FNs (filtered result)
    match_result = greedy_barline_match(filtered, gt_boxes, rule_name="center_anchor")
    fn_indices = match_result.false_negative_indices

    print(f"Total GT: {len(gt_boxes)}")
    print(f"Total Filtered: {len(filtered)}")
    print(f"FN count in filtered: {len(fn_indices)}")

    for fn_idx in fn_indices:
        gt_box = gt_boxes[fn_idx]
        print(f"\nAnalyzing FN GT Index {fn_idx}: {gt_box}")

        # Check if GT was found in probe candidates at all
        found_in_candidates = False
        best_cand = None
        best_vov = 0
        for cand in candidates:
            vov = 0
            top = max(cand[1], gt_box[1])
            bottom = min(cand[3], gt_box[3])
            if bottom > top:
                vov = (bottom - top) / max(cand[3] - cand[1], gt_box[3] - gt_box[1], 1)

            if is_barline_match(cand, gt_box, rule_name="center_anchor"):
                found_in_candidates = True
                best_cand = cand
                break
            if vov > best_vov:
                best_vov = vov
                best_cand = cand

        if found_in_candidates:
            print("  [STATUS] Present in Probe Scan candidates.")
            # Find its score in scored_data
            score = 0
            for item in scored_data:
                if tuple(item["bbox"]) == best_cand:
                    score = item["score"]
                    break
            print(f"  [SCORE] CNN Score: {score:.4f} (Threshold: 0.1)")
            if score < 0.1:
                print("  [RESULT] REJECTED by CNN Scoring.")
            else:
                print(
                    "  [RESULT] Accepted by CNN but likely dropped in Greedy Match (Wait, that shouldn't happen for FN)."
                )
        else:
            print("  [STATUS] MISSING from Probe Scan candidates.")
            print(f"  [DEBUG] Best partial match vov: {best_vov:.2f}")


if __name__ == "__main__":
    main()
