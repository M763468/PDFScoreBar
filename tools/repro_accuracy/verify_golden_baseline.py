import argparse
import json
import sys
from pathlib import Path

# Add repo root to sys path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.common.barline_evaluation import greedy_barline_match


def load_json(p):
    with open(p, "r") as f:
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


def main():
    parser = argparse.ArgumentParser(description="Verify baseline metrics.")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="data/evaluation2/golden_baseline_eval2_bc23deb",
        help="Path to the directory containing scored JSON files to verify.",
    )
    args = parser.parse_args()

    golden_root = Path(args.results_dir)
    gt_base = Path("data/evaluation2/annotations")

    datasets = [
        "Shostakovich-Festival_Overture_Va",
        "Shostakovich-Sym5-Va",
        "Sibelius-Violin_Concerto-Viola",
        "Va_Prokofiev_Symphony1",
        "Va__Prokofiev_Symphony5",
    ]

    print(f"{'Dataset':<35} | {'GT':<5} | {'TP':<5} | {'FP':<5} | {'FN':<5} | {'Recall':<8}")
    print("-" * 75)

    global_tp, global_fp, global_fn = 0, 0, 0

    for ds in datasets:
        # Match pattern: eval2_{ds}_page_{num}/*_scored.json
        scored_files = sorted(list(golden_root.glob(f"eval2_{ds}_page_*/*_scored.json")))
        gt_root = gt_base / ds

        tp, fp, fn = 0, 0, 0
        for scored_file in scored_files:
            # Extract page name (e.g. "page_001") from parent dir name
            # Parent dir: eval2_Sibelius-Violin_Concerto-Viola_page_001
            parent_dir_name = scored_file.parent.name
            page_name = "page_" + parent_dir_name.split("_page_")[1]
            gt_file = gt_root / page_name / "boxes_sorted.json"

            if not gt_file.exists():
                continue

            preds = [tuple(item["bbox"]) for item in load_json(scored_file) if item["score"] >= 0.1]
            gts = get_gt_boxes(load_json(gt_file))

            res = greedy_barline_match(
                preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0
            )
            tp += len(res.matches)
            fp += len(res.false_positive_indices)
            fn += len(res.false_negative_indices)

        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        print(f"{ds:<35} | {tp + fn:<5} | {tp:<5} | {fp:<5} | {fn:<5} | {recall:.1%}")

        global_tp += tp
        global_fp += fp
        global_fn += fn

    global_recall = global_tp / (global_tp + global_fn) if (global_tp + global_fn) > 0 else 0
    print("-" * 75)
    print(
        f"{'GLOBAL TOTAL':<35} | {global_tp + global_fn:<5} | {global_tp:<5} | {global_fp:<5} | {global_fn:<5} | {global_recall:.1%}"
    )

    expected_tp = 3580
    expected_fp = 0
    expected_fn = 1

    if global_tp != expected_tp or global_fp != expected_fp or global_fn != expected_fn:
        print(
            f"\nERROR: Baseline regression detected! Expected TP={expected_tp}, FP={expected_fp}, FN={expected_fn}"
        )
        sys.exit(1)
    else:
        print("\nSUCCESS: Golden baseline verified. No regressions.")


if __name__ == "__main__":
    main()
