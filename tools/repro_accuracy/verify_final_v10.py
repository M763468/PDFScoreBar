import json
import sys
from pathlib import Path

sys.path.append("/home/masaki_muramatsu/ws_PDFScoreBar")
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
    hybrid_dir = Path("logs/hybrid_generalization/verify_fixed_v10/20260325_130027/hybrid_results")
    gt_base = Path("data/evaluation2/annotations/Shostakovich-Festival_Overture_Va")

    tp, fp, fn = 0, 0, 0
    for json_file in sorted(hybrid_dir.glob("page_*_hybrid.json")):
        page_name = json_file.stem.replace("_hybrid", "")
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists():
            continue

        preds = [tuple(b) for b in load_json(json_file)]
        gts = get_gt_boxes(load_json(gt_file))

        # Original rule center_anchor, 12.0px threshold for 360dpi images
        res = greedy_barline_match(
            preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0
        )
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    print(f"Shostakovich (v10 + Consensus Fix) TP: {tp}, FP: {fp}, FN: {fn}")
    print(f"Recall: {recall:.2%}, Precision: {precision:.2%}")


if __name__ == "__main__":
    main()
