import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.probe_scan import run_probe_scan_batch

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
    bands_from = Path("logs/repro_v12_recovery/probe_candidates_filtered_v12")
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

        # 1. Run second Probe Scan (1x) using v12 seeds as bands_from
        # This matches exactly evaluate_full_rescue_v1.py from Issue #44
        run_probe_scan_batch(
            images=images,
            output_root=output_root,
            bands_from=bands_from,
            staff_mask_dir=None,
            clef_mask_dir=None,
            score_name=score,
            min_ratio=0.1,
            ink_threshold=210,
            input_image_scale=1.0,
            detect_probe_kwargs={
                "scan_gap_rescue": True,
                "scan_gap_threshold_ratio": 1.5,
                "scan_gap_rescue_min_ratio": 0.3,
                "scan_x_peak_rescue": True,
                "scan_rightmost_rescue": True,
                "divisi_rescue": True,
                "scan_center_on_peak": True,
                "probe_width": 2,
                "max_per_band": 100,
                "band_source": "row_stats",
            },
            enable_heuristic_filters=False,
            skip_existing=False,  # We MUST include existing_boxes!
            disable_seed_splitting=True,
        )

        # 2. Run CNN Scoring (1x)
        run_cnn_scoring_batch(
            probe_output_root=output_root,
            images=images,
            model_path=Path(
                "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
            ),
            threshold=0.1,
            batch_size=64,
            bands_from=bands_from,  # MUST BE the clean v12 seeds to ensure accurate staff_bands clustering for VOV filter
            staff_vov_threshold=0.5,
            crop_recenter_on_bbox_ink=True,
            input_image_scale=1.0,
            candidate_rescale_factor=1.0,
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
