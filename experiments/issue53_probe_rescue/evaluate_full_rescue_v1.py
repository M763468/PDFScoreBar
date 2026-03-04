from pathlib import Path

from src.pipeline.probe_scan import run_probe_scan_batch
from tools.cnn_classifier.score_candidates_batch import run_scoring_batch


def run_full_evaluation():
    # 1. Setup paths
    image_root = Path("data/evaluation2/images")
    gt_root = Path("data/evaluation2/annotations")
    bands_from = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
    output_root = Path("logs/issue53_full_eval_rescue_v1")

    # Collect all 68 pages
    images = sorted(list(image_root.rglob("page_*.png")))
    print(f"Total images to process: {len(images)}")

    # 2. Probe Scan with Gap Rescue
    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        # Baseline options
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }

    print("Step 1: Running Probe Scan with Gap Rescue...")
    run_probe_scan_batch(
        images=images,
        output_root=output_root,
        bands_from=bands_from,
        staff_mask_dir=None,  # Use row_stats fallback
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        detect_probe_kwargs=detect_probe_kwargs,
        skip_existing=True,
    )

    # 3. CNN Scoring
    print("Step 2: Running CNN Scoring...")
    model_path = Path(
        "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    )
    run_scoring_batch(
        model=model_path,
        images_root=image_root,
        logs=output_root,
        threshold=0.1,
        # Preprocessing matching baseline (croprecenter_v2)
        crop_recenter_on_bbox_ink=True,
        crop_recenter_max_shift_unit_ratio=0.5,
        # Enable staff-aware geometric filtering
        bands_from=bands_from,
        staff_vov_threshold=0.5,
        overwrite=True,
    )

    # 4. Global Evaluation (using center_anchor)
    print("Step 3: Running Global Evaluation...")
    # We can use the existing re_evaluate_global tool by creating a temp config
    eval_config = {
        "scored_root": str(output_root),
        "gt_root": str(gt_root),
        "output_csv": str(output_root / "global_summary.csv"),
        "threshold": 0.1,
        "eval_rule": "center_anchor",
        "vov_threshold": 0.5,
        "xdist_threshold": 12.0,
        "scored_glob": "*_scored.json",
    }
    config_path = output_root / "eval_config.yaml"
    import yaml

    with open(config_path, "w") as f:
        yaml.dump(eval_config, f)

    import subprocess
    import sys

    subprocess.run([sys.executable, "tools/re_evaluate_global.py", "--config", str(config_path)])


if __name__ == "__main__":
    run_full_evaluation()
