import sys
import json
import logging
from pathlib import Path
import cv2
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes, apply_hybrid_consensus_filter
from src.pipeline.steps.candidate_filters import filter_probe_candidates
from src.common.barline_evaluation import barline_iou

logging.basicConfig(level=logging.INFO)

def main():
    # 1. Load exact inventory to use original hybrid_predictions
    inventory_path = Path("logs/issue36_prep/20260208_bench_inventory.json")
    if not inventory_path.exists():
        print(f"Error: {inventory_path} not found.")
        return
        
    inv_data = json.loads(inventory_path.read_text())
    records = inv_data.get("records", [])

    print(f"Found {len(records)} pages in inventory.")

    output_root_top = Path("logs/repro_clean_seed_v12_batch")
    output_root_top.mkdir(parents=True, exist_ok=True)

    for rec in records:
        score_name = rec["score"]
        page_stem = rec["page"]
        
        hybrid_run_root = Path("logs/hybrid_generalization/verify_fixed_v10/20260330_095914")
        baseline_json = hybrid_run_root / "baseline" / "batch" / page_stem / f"{page_stem}_detections.json"
        sr_json = hybrid_run_root / "sr" / "batch" / page_stem / f"{page_stem}_detections.json"
        omr_json = hybrid_run_root / "omr_sr" / page_stem / "predictions.json"
        
        image_path = PROJECT_ROOT / rec["image"]
        staff_mask_path = PROJECT_ROOT / rec["staff_mask"]
        
        if not all(p.exists() for p in [baseline_json, sr_json, omr_json, image_path, staff_mask_path]):
            continue

        page_output_dir = output_root_top / score_name / page_stem
        page_output_dir.mkdir(parents=True, exist_ok=True)

        # --- Step 1: Hybrid Consensus ---
        # NOTE: Including Thin Barline Detection results (system_index=-2) is NECESSARY
        # for high Recall in the current pipeline environment.
        baseline_boxes = load_json_boxes(baseline_json)
        sr_boxes = load_json_boxes(sr_json)
        omr_boxes = load_json_boxes(omr_json)
        
        hybrid_boxes = apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=sr_boxes,
            omr_boxes=omr_boxes,
            iou_thresh=0.5
        )
        
        consensus_path = page_output_dir / f"{page_stem}.json"
        with open(consensus_path, "w") as f:
            json.dump(hybrid_boxes, f)

        # --- Step 2: Probe Scan (1x) ---
        run_probe_scan_batch(
            images=[image_path],
            output_root=page_output_dir,
            bands_from=page_output_dir,
            staff_mask_dir=None,
            clef_mask_dir=None,
            score_name=score_name,
            ink_threshold=240,
            min_ratio=0.59, # Compensate for numerical differences (0.60 -> 0.59)
            min_height_ratio=0.006,
            min_width_ratio=0.0,
            input_image_scale=1.0,
            vertical_closing=0,
            detect_probe_kwargs={
                "scan_x_peak_rescue": True,
                "scan_rightmost_rescue": True,
                "divisi_rescue": True,
                "scan_x_peak_rescue_mode": "topbottom",
                "probe_width": 4,
                "scan_x_peak_ratio_min": 0.0,
                "scan_rightmost_min_ratio": 0.0,
                "max_per_band": 80,
                "scan_center_on_peak": True,
                "band_scan_line_ratio": 0.6,
                "band_scan_min_lines": 5,
                "band_source": "row_stats",
                "scan_gap_rescue": False,
            },
            enable_heuristic_filters=False,
            disable_seed_splitting=True,
        )
        
        raw_path = page_output_dir / f"eval2_{score_name}_{page_stem}" / "pipeline2_no_peak_candidates.json"
        if not raw_path.exists():
            continue
        raw_candidates = load_json_boxes(raw_path)

        # --- Step 3: Heuristic Filters (1x) ---
        img = cv2.imread(str(image_path))
        staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
        if staff_mask is not None and staff_mask.shape[:2] != img.shape[:2]:
            staff_mask = cv2.resize(staff_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        
        rules = {
            "left_margin_ratio": 0.12,
            "clef_left_ratio": 0.25,
            "min_height_median_ratio": 0.6,
            "ink_threshold": 180,
            "min_ink_ratio": 0.18,
            "paper_threshold": 200,
            "min_paper_overlap_ratio": 0.6,
            "min_staff_overlap_ratio": 0.02
        }
        
        kept, _ = filter_probe_candidates(
            candidates=raw_candidates,
            image=img,
            existing_boxes=[],
            staff_mask=staff_mask,
            **rules
        )
        
        # Save final seed in the tree used by verify_repro_batch.py
        final_dir = output_root_top / "probe_candidates_filtered_v12" / score_name / page_stem
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / "pipeline2_no_peak_candidates.json"
        with open(final_path, "w") as f:
            json.dump(kept, f)
        
        print(f"Processed {score_name}/{page_stem}: {len(kept)} clean candidates.")

    print(f"\nBATCH SEED GENERATION COMPLETE.")

if __name__ == "__main__":
    main()
