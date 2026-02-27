import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.pipeline.io import ensure_dir
from src.pipeline.probe_scan import run_probe_scan_batch

logging.basicConfig(level=logging.INFO)

# Experiment ID: E46-A02-SPLIT-CONSERVATIVE
# Goal: Reduce Track-A split FP while keeping FN_det gains on the target pages.

TARGET_PAGES = [
    ("Sibelius-Violin_Concerto-Viola", "page_001"),
    ("Sibelius-Violin_Concerto-Viola", "page_004"),
    ("Sibelius-Violin_Concerto-Viola", "page_008"),
    ("Sibelius-Violin_Concerto-Viola", "page_010"),
    ("Va_Prokofiev_Symphony1", "page_001"),
    ("Va__Prokofiev_Symphony5", "page_003"),
    ("Va__Prokofiev_Symphony5", "page_008"),
    ("Va__Prokofiev_Symphony5", "page_015"),
    ("Va__Prokofiev_Symphony5", "page_016"),
]

IMAGE_ROOT = Path("data/evaluation2/images")
HYBRID_ROOT = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
OUTPUT_ROOT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_track_a_split_v2_conservative"
)
CNN_MODEL = "logs/cnn_barline_classification/issue44_baseline_v1/cnn_classifier_best.pth"

# Conservative split parameters to suppress over-splitting FP.
DET_CFG = {
    "min_peak_distance_unit_ratio": 0.6,
    "x_merge_tol_unit_ratio": 0.4,
    "post_emit_unit_normalized_box": True,
    "post_norm_width_unit_ratio": 0.8,
    "post_norm_height_unit_ratio": 4.0,
    "post_split_wide_candidates": True,
    "post_split_min_width_unit_ratio": 1.5,
    "post_split_box_width_unit_ratio": 0.8,
    "post_split_peak_distance_unit_ratio": 0.6,
    "post_split_peak_prominence_ratio": 0.25,
}


def run_experiment():
    ensure_dir(OUTPUT_ROOT)

    image_paths = []
    for score, page in TARGET_PAGES:
        img_path = IMAGE_ROOT / score / f"{page}.png"
        if img_path.exists():
            image_paths.append(img_path)
        else:
            print(f"Warning: Image not found {img_path}")

    print(f"Running probe scan for {len(image_paths)} pages...")
    run_probe_scan_batch(
        images=image_paths,
        output_root=OUTPUT_ROOT,
        bands_from=HYBRID_ROOT,
        staff_mask_dir=HYBRID_ROOT,
        ink_threshold=230,
        min_ratio=0.70,
        min_height_ratio=0.012,
        detect_probe_kwargs=DET_CFG,
    )

    print(f"Running CNN scoring for {len(image_paths)} pages...")
    import subprocess
    import sys

    temp_cfg = {
        "model_path": CNN_MODEL,
        "threshold": 0.1,
        "crop_recenter_on_bbox_ink": True,
        "crop_recenter_apply_if_width_ge_unit_ratio": 0.4,
    }
    temp_cfg_path = OUTPUT_ROOT / "temp_scoring_cfg.yaml"
    import yaml

    with open(temp_cfg_path, "w") as f:
        yaml.dump(temp_cfg, f)

    cmd = [
        sys.executable,
        "tools/cnn_classifier/score_candidates_batch.py",
        "--config",
        str(temp_cfg_path),
        "--logs",
        str(OUTPUT_ROOT),
        "--model",
        str(CNN_MODEL),
    ]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print("Experiment complete.")


if __name__ == "__main__":
    run_experiment()
