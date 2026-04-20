import json
import logging
import sys
from pathlib import Path

import cv2

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.steps.candidate_filters import filter_probe_candidates

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.steps.probe_scan import run_probe_scan_batch

logging.basicConfig(level=logging.INFO)

# Constants for easy configuration
INVENTORY_PATH = Path("logs/issue36_prep/20260208_bench_inventory.json")
RUN_ROOT = Path("logs/hybrid_generalization/verify_fixed_v10")

# Mapping from score name to the specific timestamp subdirectory in verify_fixed_v10
SCORE_TO_RUN = {
    "Shostakovich-Festival_Overture_Va": "20260324_121505",
    "Shostakovich-Sym5-Va": "20260330_034727",
    "Sibelius-Violin_Concerto-Viola": "20260330_042631",
    "Va_Prokofiev_Symphony1": "20260330_044952",
    "Va__Prokofiev_Symphony5": "20260330_095914",
}

OUTPUT_ROOT_TOP = Path("logs/repro_v12_recovery_final")


def main():
    if not INVENTORY_PATH.exists():
        print(f"Error: {INVENTORY_PATH} not found.")
        return

    inv_data = json.loads(INVENTORY_PATH.read_text())
    records = inv_data.get("records", [])

    print(f"Found {len(records)} pages in inventory.")

    output_root_top = OUTPUT_ROOT_TOP
    output_root_top.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    missing_count = 0

    for rec in records:
        score_name = rec["score"]
        page_stem = rec["page"]

        if score_name not in SCORE_TO_RUN:
            print(f"Warning: No run mapping for {score_name}. Skipping.")
            continue

        hybrid_sub_root = RUN_ROOT / SCORE_TO_RUN[score_name]

        # Use robust path lookup
        baseline_json = (
            hybrid_sub_root / "baseline" / "batch" / page_stem / f"{page_stem}_detections.json"
        )
        sr_json = hybrid_sub_root / "sr" / "batch" / page_stem / f"{page_stem}_detections.json"

        # OMR may be in omr_sr or omr_sr/batch (check existing)
        omr_json = hybrid_sub_root / "omr_sr" / page_stem / "predictions.json"
        if not omr_json.exists():
            omr_json = (
                hybrid_sub_root / "omr_sr" / "batch" / page_stem / f"{page_stem}_detections.json"
            )

        image_path = PROJECT_ROOT / rec["image"]
        staff_mask_path = PROJECT_ROOT / rec["staff_mask"]

        if not all(
            p.exists() for p in [baseline_json, sr_json, omr_json, image_path, staff_mask_path]
        ):
            # print(f"Missing files for {score_name}/{page_stem}. Skipping.")
            missing_count += 1
            continue

        page_output_dir = output_root_top / score_name / page_stem
        page_output_dir.mkdir(parents=True, exist_ok=True)

        # --- Step 1: Hybrid Consensus ---
        # The reference runs may have been done at various resolutions (e.g. 600 DPI or 424 DPI).
        # We must scale them to match the target evaluation image (usually 300 DPI).
        ref_img = cv2.imread(str(baseline_json.parent / f"{page_stem}.png"))
        eval_img = cv2.imread(str(image_path))
        if ref_img is None or eval_img is None:
            print(f"Error loading images for scaling check: {page_stem}")
            continue

        ref_h, ref_w = ref_img.shape[:2]
        eval_h, eval_w = eval_img.shape[:2]
        dyn_scale = eval_w / ref_w
        if abs(dyn_scale - 1.0) > 0.01:
            print(f"INFO: Dynamic scale for {page_stem}: {dyn_scale:.4f} ({ref_w} -> {eval_w})")

        baseline_boxes = load_json_boxes(baseline_json)
        sr_boxes = load_json_boxes(sr_json)
        omr_boxes = load_json_boxes(omr_json)

        # 2. Extract and Scale Boxes
        # We use UNION of all available sources to maximize recall
        all_scaled_boxes = []

        for boxes_list in [baseline_boxes, sr_boxes, omr_boxes]:
            if not boxes_list:
                continue
            # Deduplicate and scale
            for b in boxes_list:
                sb = (
                    int(b[0] * dyn_scale),
                    int(b[1] * dyn_scale),
                    int(b[2] * dyn_scale),
                    int(b[3] * dyn_scale),
                )
                all_scaled_boxes.append(sb)

        # 3. Final Deduplication (greedy)
        if not all_scaled_boxes:
            print(f"[{page_stem}] ERROR: No boxes found in any source")
            continue

        def barline_iou(boxA, boxB):
            xA = max(boxA[0], boxB[0])
            yA = max(boxA[1], boxB[1])
            xB = min(boxA[2], boxB[2])
            yB = min(boxA[3], boxB[3])
            interArea = max(0, xB - xA) * max(0, yB - yA)
            boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
            boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
            return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

        # 3. Final Deduplication (greedy)
        # Relaxed slightly to avoid losing Divisi barlines while keeping seeds clean
        final_seeds = []
        sorted_boxes = sorted(all_scaled_boxes, key=lambda x: x[0])
        for b in sorted_boxes:
            if not any(barline_iou(b, fb) > 0.8 for fb in final_seeds):
                final_seeds.append(b)

        hybrid_boxes = final_seeds

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
            min_ratio=0.1,  # Broad scan for maximum recall
            min_height_ratio=0.0,  # Handled by Step 3
            min_width_ratio=0.0,
            input_image_scale=1.0,
            vertical_closing=4,
            detect_probe_kwargs={
                "scan_gap_rescue": True,
                "scan_gap_threshold_ratio": 1.8,
                "scan_gap_rescue_min_ratio": 0.0,
                "scan_gap_margin_ratio": 0.1,
                "scan_x_peak_rescue": True,
                "scan_rightmost_rescue": True,
                "divisi_rescue": True,
                "scan_x_peak_rescue_mode": "topbottom",
                "probe_width": 4,
                "scan_x_peak_ratio_min": 0.0,
                "scan_rightmost_min_ratio": 0.0,
                "max_per_band": 100,
                "scan_center_on_peak": True,
                "band_scan_line_ratio": 0.6,
                "band_scan_min_lines": 5,
                "band_source": "row_stats",
                "min_peak_distance_unit_ratio": 0.12,
            },
            enable_heuristic_filters=False,
            disable_seed_splitting=False,
        )

        raw_path = (
            page_output_dir
            / f"eval2_{score_name}_{page_stem}"
            / "pipeline2_no_peak_candidates.json"
        )
        if not raw_path.exists():
            continue
        raw_candidates = load_json_boxes(raw_path)

        # Apply strict filters to ensure seeds are clean (Step 3 in docs)
        img = cv2.imread(str(image_path))
        staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
        if staff_mask is not None and staff_mask.shape[:2] != img.shape[:2]:
            staff_mask = cv2.resize(
                staff_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
            )

        rules = {
            "left_margin_ratio": 0.12,
            "clef_left_ratio": 0.25,
            "min_height_median_ratio": 0.4,  # Optimized ratio for Divisi
            "ink_threshold": 180,
            "min_ink_ratio": 0.18,  # Golden Baseline
            "paper_threshold": 200,
            "min_paper_overlap_ratio": 0.6,
            "min_staff_overlap_ratio": 0.02,  # Golden Baseline
        }

        kept, _ = filter_probe_candidates(
            candidates=raw_candidates, image=img, existing_boxes=[], staff_mask=staff_mask, **rules
        )

        # Save final seed in the tree used by verify_repro_batch.py
        final_dir = output_root_top / "probe_candidates_filtered_v12" / score_name / page_stem
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / "pipeline2_no_peak_candidates.json"
        with open(final_path, "w") as f:
            json.dump(kept, f)

        processed_count += 1
        if processed_count % 10 == 0:
            print(f"Processed {processed_count} pages...")

    print(
        f"\nBATCH SEED GENERATION COMPLETE. Processed: {processed_count}, Missing: {missing_count}"
    )


if __name__ == "__main__":
    main()
