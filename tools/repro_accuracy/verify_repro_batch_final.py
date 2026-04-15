import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

logging.basicConfig(level=logging.INFO)


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def get_gt_boxes(gt_data):
    boxes = []
    for item in gt_data:
        if isinstance(item, list):
            boxes.append(tuple(item[:4]))
        elif "barline_location" in item:
            boxes.append(tuple(item["barline_location"]))
    return boxes


def main():
    # Final seeds we just generated
    bands_from = Path("logs/repro_v12_recovery_final/probe_candidates_filtered_v12")
    image_root = Path("data/evaluation2/images")
    output_root = Path("logs/repro_v12_recovery/verify_final/probe_scan")

    if not bands_from.exists():
        print(f"Error: {bands_from} not found. Run the seed generation script first.")
        return

    # Identify scores
    scores = sorted([d.name for d in bands_from.iterdir() if d.is_dir()])

    global_tp, global_fp, global_fn = 0, 0, 0

    for score in scores:
        print(f"\nEvaluating {score}...")
        image_dir = image_root / score
        images = sorted(list(image_dir.glob("*.png")))

        # 1. Skip second Probe Scan, use seeds directly
        for img in images:
            page_stem = img.stem
            seed_path = bands_from / score / page_stem / "pipeline2_no_peak_candidates.json"
            if not seed_path.exists():
                continue

            run_id = f"eval2_{score}_{page_stem}"
            dest_dir = output_root / run_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy(seed_path, dest_dir / "pipeline2_no_peak_candidates.json")

        # 2. Run CNN Scoring (1x)
        run_cnn_scoring_batch(
            probe_output_root=output_root,
            images=images,
            model_path=Path(
                "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
            ),
            threshold=0.1,
            batch_size=64,
            bands_from=bands_from,
            staff_vov_threshold=0.5,
            crop_recenter_on_bbox_ink=True,
            input_image_scale=1.0,
        )

        # 3. Evaluate
        gt_base = Path("data/evaluation2/annotations") / score
        tp, fp, fn = 0, 0, 0

        for img in images:
            page_name = "page_" + img.stem.split("_")[-1]
            gt_file = gt_base / page_name / "boxes_sorted.json"
            scored_file = (
                output_root / f"eval2_{score}_{img.stem}" / "pipeline2_no_peak_scored.json"
            )

            if not gt_file.exists() or not scored_file.exists():
                continue

            data = load_json(scored_file)
            preds = [tuple(c["bbox"]) for c in data if c["score"] >= 0.1]
            gts = get_gt_boxes(load_json(gt_file))

            # Using 30.0 for xdist_threshold as in original evaluate_full_rescue_v1.py evaluation logic
            res = greedy_barline_match(
                preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0
            )
            tp += len(res.matches)
            fp += len(res.false_positive_indices)
            fn += len(res.false_negative_indices)

        print(f"Result for {score}: TP: {tp} | FP: {fp} | FN: {fn}")
        global_tp += tp
        global_fp += fp
        global_fn += fn

    print("-" * 50)
    print(f"GLOBAL TOTAL: TP: {global_tp} | FP: {global_fp} | FN: {global_fn}")
    if (global_tp + global_fn) > 0:
        print(f"Recall: {global_tp / (global_tp + global_fn):.1%}")
    if (global_tp + global_fp) > 0:
        print(f"Precision: {global_tp / (global_tp + global_fp):.1%}")


if __name__ == "__main__":
    main()
