import json
import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes
from src.common.barline_evaluation import greedy_barline_match


def eval_json(pred_path, gt_path):
    with open(pred_path) as f:
        data = json.load(f)

    # Handle homr detections.json format
    if isinstance(data, dict) and "predictions" in data:
        preds = [tuple(p["orig_bbox"]) for p in data["predictions"]]
    else:
        preds = [tuple(b) for b in data]

    gt_boxes = load_ground_truth_boxes(Path(gt_path))

    match_result = greedy_barline_match(
        preds, gt_boxes, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0
    )

    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return {"P": precision, "R": recall, "F1": f1, "TP": tp, "FP": fp, "FN": fn}


def main():
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )

    x4_path = PROJECT_ROOT / "artifacts/manual_sr_x4/sr4/page_001/page_001_detections.json"
    x2_path = PROJECT_ROOT / "artifacts/manual_sr_x2/sr2/page_001/page_001_detections.json"
    bypass_path = (
        PROJECT_ROOT
        / "logs/hybrid_generalization/bypass_sr_test/eval2_bypass_sr_test_v2/baseline/batch/page_001/page_001_detections.json"
    )

    print("--- SR x4 (Reference) ---")
    print(eval_json(x4_path, gt_path))

    print("\n--- SR x2 (Native) ---")
    print(eval_json(x2_path, gt_path))

    print("\n--- SR Bypass (Baseline homr) ---")
    print(eval_json(bypass_path, gt_path))


if __name__ == "__main__":
    main()
