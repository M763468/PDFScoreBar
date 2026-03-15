import json
import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.core.metrics import load_ground_truth_boxes
from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
)


def main():
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )
    run_dir = (
        PROJECT_ROOT
        / "logs/full_pipeline_runs/bypass_sr_test/eval2_bypass_sr_test_v2/intermediate/probe_scan/eval2_images_page_001"
    )
    filtered_path = run_dir / "pipeline2_no_peak_filtered_cnn.json"

    gt_boxes = load_ground_truth_boxes(gt_path)
    with open(filtered_path) as f:
        filtered = [tuple(b) for b in json.load(f)]

    match_result = greedy_barline_match(filtered, gt_boxes, rule_name="center_anchor")

    print(f"FN Indices: {match_result.false_negative_indices}")

    for fn_idx in match_result.false_negative_indices:
        gt_box = gt_boxes[fn_idx]
        print(f"\nGT {fn_idx}: {gt_box}")

        # See if any pred matches this GT
        matches = []
        for p_idx, pred in enumerate(filtered):
            vov = barline_vertical_overlap(pred, gt_box)
            xdist = center_distance_x(pred, gt_box)
            if vov >= 0.5 and xdist <= 12.0:
                matches.append((p_idx, pred, vov, xdist))

        if matches:
            print(f"  Found {len(matches)} potential matches in filtered:")
            for p_idx, pred, vov, xdist in matches:
                # Check if this pred was matched to ANOTHER GT
                matched_gt = None
                for m in match_result.matches:
                    if m.pred_index == p_idx:
                        matched_gt = m.gt_index
                        break
                print(
                    f"    Pred {p_idx}: {pred} (vov={vov:.2f}, xdist={xdist:.2f}) -> Matched to GT {matched_gt}"
                )
        else:
            print("  No potential matches in filtered.")


if __name__ == "__main__":
    main()
