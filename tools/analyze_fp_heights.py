import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))
from src.common.barline_evaluation import greedy_barline_match


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", required=True)
    parser.add_argument("--gt-root", required=True)
    args = parser.parse_args()

    fp_heights = []
    tp_heights = []

    # We will look at pages known to have FPs from the inventory
    target_pages = [
        "prokofiev5_page_001",
        "prokofiev5_page_003",
        "prokofiev5_page_005",
        "prokofiev5_page_011",
        "prokofiev5_page_013",
        "prokofiev5_page_017",
        "Shosrakovich-Sym5-Va_page_016",
        "Shosrakovich-Sym5-Va_page_018",
        "Shosrakovich-Sym5-Va_page_019",
        "Sibelius-Violin_Concerto-Viola_page_006",
        "Va_Prokofiev_Symphony1_page_004",
        "Va_Prokofiev_Symphony1_page_005",
    ]

    for subdir_page in target_pages:
        # Construct path usually: logs/global_extreme_test/eval2_{subdir_page}
        # But wait, directory names in logs have 'eval2_' prefix.
        run_dir = Path(args.scored_root) / f"eval2_{subdir_page}"
        json_path = run_dir / "pipeline2_no_peak_scored.json"

        if not json_path.exists():
            print(f"Skipping {subdir_page}, not found")
            continue

        with open(json_path) as f:
            candidates = json.load(f)

        # Parse page info for GT
        parts = subdir_page.split("_")
        try:
            page_idx = parts.index("page")
            subdir = "_".join(parts[:page_idx])
            page_name = "_".join(parts[page_idx:])
        except:
            continue

        # GT Path
        gt_dir = Path(args.gt_root) / subdir / page_name
        if not gt_dir.exists():
            gt_dir = Path(args.gt_root) / page_name  # Try flat

        gt_files = list(gt_dir.glob("boxes_sorted*.json"))
        if not gt_files:
            continue
        gt_files.sort(reverse=True)

        with open(gt_files[0]) as f:
            gt_data = json.load(f)

        gt_boxes = []
        for item in gt_data:
            if isinstance(item, list):
                gt_boxes.append(tuple(item[:4]))
            elif isinstance(item, dict):
                if "box" in item:
                    gt_boxes.append(tuple(item["box"]))
                elif "barline_location" in item:
                    gt_boxes.append(tuple(item["barline_location"]))

        # Filter candidates (threshold 0.1)
        accepted = [c for c in candidates if c["score"] > 0.1]
        accepted_boxes = [tuple(c["bbox"]) for c in accepted]

        match = greedy_barline_match(accepted_boxes, gt_boxes)

        for idx in match.false_positive_indices:
            b = accepted_boxes[idx]
            h = abs(b[3] - b[1])
            fp_heights.append((subdir_page, h))

        for m in match.matches:
            b = accepted_boxes[m.pred_index]
            h = abs(b[3] - b[1])
            tp_heights.append(h)

    print(f"Total FPs analyzed: {len(fp_heights)}")
    print(f"FP Heights: {sorted([f'{h:.1f}' for _, h in fp_heights])}")
    print(f"Total TPs analyzed: {len(tp_heights)}")
    if tp_heights:
        print(f"TP Height Min: {min(tp_heights)}")
        print(f"TP Height Max: {max(tp_heights)}")
        print(f"TP Height Avg: {np.mean(tp_heights):.1f}")

    # Check overlap
    if tp_heights:
        min_tp = min(tp_heights)
        short_fps = [h for _, h in fp_heights if h < min_tp]
        print(f"FPs shorter than shortest TP ({min_tp}): {len(short_fps)}")
        for name, h in fp_heights:
            if h < min_tp:
                print(f"  Short FP: {name} h={h:.1f}")


if __name__ == "__main__":
    main()
