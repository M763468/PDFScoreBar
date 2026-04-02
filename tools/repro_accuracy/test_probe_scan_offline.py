import sys
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

logging.basicConfig(level=logging.INFO)

def main():
    images = [Path("data/evaluation2/images/Va__Prokofiev_Symphony5/page_005.png")]
    
    print(f"Collected {len(images)} images")
    
    bands_from = Path("logs/hybrid_generalization/verify_fixed_v10/20260330_095914")
    output_root = Path("logs/full_pipeline_runs/verify_v10_prokofiev5_filtered_v4/intermediate/probe_scan")
    
    filter_kwargs = {
        "left_margin_ratio": 0.12,
        "clef_left_ratio": 0.25,
        "min_height_median_ratio": 0.3,
        "ink_threshold": 180,
        "min_ink_ratio": 0.18,
        "paper_threshold": 200,
        "min_staff_overlap_ratio": 0.05,
    }
    
    print("Running probe scan...")
    run_probe_scan_batch(
        images=images,
        output_root=output_root,
        bands_from=bands_from,
        staff_mask_dir=bands_from,
        clef_mask_dir=bands_from,
        ink_threshold=210,
        min_ratio=0.10,
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        score_name="Va__Prokofiev_Symphony5",
        band_cluster_max_dist=None,
        band_min_row_count=1,
        vertical_closing=4,
        skip_existing=False,
        input_image_scale=2.0,
        detect_probe_kwargs={
            "scan_x_peak_rescue": True,
            "scan_x_peak_ratio_min": 1.2,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "scan_gap_rescue": True,
            "max_per_band": 200,
            "band_source": "row_stats",
            "probe_width": 2,
        },
        enable_heuristic_filters=True,
        candidate_filter_kwargs=filter_kwargs,
    )
    
    print("Running CNN scoring...")
    run_cnn_scoring_batch(
        probe_output_root=output_root,
        images=images,
        model_path=Path("logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"),
        threshold=0.4,
        batch_size=32,
    )

if __name__ == "__main__":
    main()
