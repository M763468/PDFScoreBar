import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from src.common.barline_evaluation import greedy_barline_match


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def get_gt_boxes(gt_data):
    return [tuple(item["barline_location"]) for item in gt_data if "barline_location" in item]


def verify_dataset(dataset_name, run_path):
    scored_dir = run_path / "intermediate/probe_scan"
    gt_base = Path(f"data/evaluation2/annotations/{dataset_name}")
    tp, fp, fn = 0, 0, 0
    for scored_file in sorted(scored_dir.rglob("pipeline2_no_peak_scored.json")):
        parts = scored_file.parent.name.split("_")
        page_name = parts[-2] + "_" + parts[-1]
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists():
            continue
        data = load_json(scored_file)
        # Standard threshold verified in Issue 117
        preds = [tuple(c["bbox"]) for c in data if c["score"] >= 0.4]
        gts = get_gt_boxes(load_json(gt_file))
        res = greedy_barline_match(
            preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0
        )
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)
    return tp, fp, fn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=str, help="Path to the full_pipeline_run directory")
    args = parser.parse_args()

    if args.run_dir:
        run_path = Path(args.run_dir)
        manifest = load_json(run_path / "manifest.json")
        pdf_name = Path(manifest["config"]["inputs"]["pdf_path"]).stem
        tp, fp, fn = verify_dataset(pdf_name, run_path)
        print(
            f"{pdf_name:<35} | R: {tp / (tp + fn):.1%} | P: {tp / (tp + fp):.1%} | TP: {tp} | FP: {fp} | FN: {fn}"
        )
    else:
        print("Please provide --run-dir")


if __name__ == "__main__":
    main()
