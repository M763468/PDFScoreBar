import json
import shutil
import sys
import time
from pathlib import Path

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes
from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.probe_scan import run_probe_scan_batch
from src.pipeline.run_ids import build_probe_run_id


def main():
    original_bands_root = (
        PROJECT_ROOT / "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
    )
    upscale_root = PROJECT_ROOT / "artifacts/issue25_x2_exact_verification/upscaled_images"
    image_root = PROJECT_ROOT / "data/evaluation2/images"
    gt_root = PROJECT_ROOT / "data/evaluation2/annotations"

    output_root = PROJECT_ROOT / "artifacts/issue25_global_verification_final"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    cnn_model_path = (
        PROJECT_ROOT
        / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    )

    available_pages = []
    for score_dir in sorted(original_bands_root.iterdir()):
        if not score_dir.is_dir():
            continue
        score_name = score_dir.name
        for stem_dir in sorted(score_dir.iterdir()):
            if not stem_dir.is_dir():
                continue
            stem = stem_dir.name
            available_pages.append((score_name, stem))

    results = []

    for scale, name in [(1.0, "Bypass"), (2.0, "SRx2")]:
        print(f"\n>>> Running Global Verification: {name} (Scale {scale})")
        probe_output_root = output_root / f"probe_scan_{name}"
        probe_output_root.mkdir(parents=True)

        target_tasks = []
        for s_name, stem in available_pages:
            orig_img = image_root / s_name / f"{stem}.png"
            upscaled_img = upscale_root / s_name / stem / stem / f"{stem}.png"
            img_to_use = orig_img if scale == 1.0 else upscaled_img
            if img_to_use.exists():
                target_tasks.append((img_to_use, s_name, stem))

        start_time = time.time()

        # PROCESS ONE BY ONE TO BE ABSOLUTELY SURE ABOUT RUN_ID
        for img_p, s_name, stem in tqdm(target_tasks, desc=f"Processing {name}"):
            # 1. Probe Scan
            run_probe_scan_batch(
                images=[img_p],
                output_root=probe_output_root,
                bands_from=original_bands_root,
                staff_mask_dir=None,
                ink_threshold=180,
                min_ratio=0.85,
                min_height_ratio=0.012,
                score_name=s_name,  # FORCE score_name
                input_image_scale=scale,
                detect_probe_kwargs={
                    "scan_center_on_peak": True,
                    "max_per_band": 200,
                    "post_split_wide_candidates": True,
                    "post_split_min_width_unit_ratio": 0.5,
                    "post_split_box_width_unit_ratio": 0.4,
                    "post_split_peak_distance_unit_ratio": 0.3,
                },
            )
            # 2. CNN Scoring
            run_cnn_scoring_batch(
                probe_output_root=probe_output_root,
                images=[img_p],
                model_path=cnn_model_path,
                threshold=0.1,
                score_name=s_name,  # FORCE score_name
                crop_recenter_on_bbox_ink=True,
                crop_recenter_max_shift_unit_ratio=0.5,
                input_image_scale=scale,
            )

        duration = time.time() - start_time

        # 3. Evaluation
        total_tp, total_gt = 0, 0
        total_fn = 0
        for _, s_name, stem in target_tasks:
            # build_probe_run_id with score_name=s_name is reliable
            run_id = build_probe_run_id(_, score_name=s_name)
            scored_path = probe_output_root / run_id / "pipeline2_no_peak_filtered_cnn.json"
            gt_path = gt_root / s_name / stem / "boxes_sorted.json"

            if not scored_path.exists():
                print(f"Missing: {scored_path}")
                continue

            with open(scored_path) as f:
                preds = [tuple(p) for p in json.load(f)]
            gt_boxes = load_ground_truth_boxes(gt_path)
            match_result = greedy_barline_match(preds, gt_boxes, rule_name="center_anchor")
            total_tp += len(match_result.matches)
            total_gt += len(gt_boxes)
            total_fn += len(match_result.false_negative_indices)

        recall = total_tp / total_gt if total_gt > 0 else 0
        results.append(
            {
                "name": name,
                "recall": recall,
                "tp": total_tp,
                "fn": total_fn,
                "gt": total_gt,
                "avg_speed": duration / len(target_tasks),
            }
        )

    print("\n" + "=" * 80)
    print(f"{'Mode':<10} | {'Recall':<10} | {'TP/GT':<15} | {'Speed':<10}")
    print("-" * 80)
    for r in results:
        print(
            f"{r['name']:<10} | {r['recall']:>9.2%} | {r['tp']:>4}/{r['gt']:<4} | {r['avg_speed']:>6.2f}s/p"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
