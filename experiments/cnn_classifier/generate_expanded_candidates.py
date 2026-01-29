import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

# Import logic from the existing tool
from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan


def process_page(run_dir: Path, image_root: Path):
    # Infer image path from run_dir name (eval2_subdir_page_name)
    run_id = run_dir.name
    parts = run_id.split("_")
    try:
        page_idx = parts.index("page")
        subdir = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])
        image_rel = Path(subdir) / f"{page_name}.png"
        image_path = image_root / image_rel
    except ValueError:
        print(f"Skipping {run_id}: Cannot parse page name")
        return

    if not image_path.exists():
        print(f"Skipping {run_id}: Image not found at {image_path}")
        return

    # Load Image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Skipping {run_id}: Failed to load image")
        return

    # Staff mask is not needed for band_source="row_stats"
    # We use existing predictions to define the bands.
    staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)  # Dummy mask

    # Load Existing Boxes (Baseline Hybrid Predictions)
    hybrid_json = run_dir / "hybrid_predictions.json"
    existing_boxes = []
    if hybrid_json.exists():
        with open(hybrid_json, "r") as f:
            data = json.load(f)
            # Handle list of lists or dicts
            for item in data:
                if isinstance(item, list):
                    existing_boxes.append(tuple(item))
                elif isinstance(item, dict):
                    existing_boxes.append(tuple(item.get("bbox", [])))

    if not existing_boxes:
        # If no existing boxes, we can't build row_stats.
        # In this case we might want to skip or try staff mask if available?
        # For now, skip, as "Candidate Expansion" usually implies expanding existing stuff.
        print(f"Skipping {run_id}: No existing boxes to build bands from")
        return

    # --- Step 1: Raw Probe Scan (Rescue Enabled) ---
    # Params based on "best repro" and user request
    candidates_raw = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # Standard Scan Params (defaults from run_gt_rebuild... source)
        probe_width=4,
        ink_threshold=180,
        min_ratio=0.85,
        scan_center_on_peak=True,
        # KEY CHANGE: Use row_stats from existing boxes instead of staff mask
        band_source="row_stats",
    )

    # Combine: Raw = Existing + New Probe Results
    final_raw = set(existing_boxes)
    for c in candidates_raw:
        final_raw.add(c)

    final_raw_list = sorted(list(final_raw))

    # Save Raw
    out_raw = run_dir / "expanded_candidates_raw.json"
    with open(out_raw, "w") as f:
        json.dump(final_raw_list, f, indent=2)

    # --- Step 2: Relaxed Probe Scan (More Recall) ---
    # User requested looser thresholds to catch FNs.
    candidates_relaxed = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # RELAXED Thresholds
        probe_width=4,
        ink_threshold=180,
        min_ratio=0.70,  # Lowered from 0.85
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=1.4,  # Lowered from 1.6 (default)
        scan_rightmost_min_ratio=0.70,  # Lowered from 0.85 (default)
        # Source
        band_source="row_stats",
    )

    # Combine
    final_relaxed = set(existing_boxes)
    for c in candidates_relaxed:
        final_relaxed.add(c)

    final_relaxed_list = sorted(list(final_relaxed))

    # Save Relaxed
    out_relaxed = run_dir / "expanded_candidates_relaxed.json"
    with open(out_relaxed, "w") as f:
        json.dump(final_relaxed_list, f, indent=2)

    # --- Step 3: Ultraloose Probe Scan (Aggressive Recall) ---
    # Attempting to reach FN=0 by very loose thresholds
    candidates_ultraloose = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # ULTRALOOSE Thresholds
        probe_width=4,
        ink_threshold=200,  # Higher to catch faint ink (0-200 considered ink)
        min_ratio=0.50,  # Drastically lowered
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=1.2,  # Very low peak requirement
        scan_rightmost_min_ratio=0.50,
        # Source
        band_source="row_stats",
    )

    # Combine
    final_ultraloose = set(existing_boxes)
    for c in candidates_ultraloose:
        final_ultraloose.add(c)

    final_ultraloose_list = sorted(list(final_ultraloose))

    # Save Ultraloose
    out_ultraloose = run_dir / "expanded_candidates_ultraloose.json"
    with open(out_ultraloose, "w") as f:
        json.dump(final_ultraloose_list, f, indent=2)

    # --- Step 4: User Specified Params ---
    # probe_width=2, ink=180, ratio=0.5
    candidates_user = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # USER Params
        probe_width=2,  # Thinner probe
        ink_threshold=180,  # Standard ink
        min_ratio=0.50,  # Low ratio
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=1.2,  # Matching Ultraloose assumption
        scan_rightmost_min_ratio=0.50,  # Matching min_ratio
        # Source
        band_source="row_stats",
    )

    # Combine
    final_user = set(existing_boxes)
    for c in candidates_user:
        final_user.add(c)

    final_user_list = sorted(list(final_user))

    # Save User
    out_user = run_dir / "expanded_candidates_user.json"
    with open(out_user, "w") as f:
        json.dump(final_user_list, f, indent=2)

    # --- Step 5: Hyperlapse Probe Scan (Max Recall) ---
    # User requested to catch EVERYTHING, accepting noise.
    candidates_hyper = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # HYPERLAPSE Thresholds
        probe_width=4,
        ink_threshold=220,  # Very sensitive to faint ink (almost any gray)
        min_ratio=0.10,  # Accept almost any vertical interruptions
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=1.01,  # Disable peak dominance check (accept flat peaks)
        scan_rightmost_min_ratio=0.10,
        # Source
        band_source="row_stats",
    )

    # Combine
    final_hyper = set(existing_boxes)
    for c in candidates_hyper:
        final_hyper.add(c)

    final_hyper_list = sorted(list(final_hyper))

    # Save Hyper
    out_hyper = run_dir / "expanded_candidates_hyper.json"
    with open(out_hyper, "w") as f:
        json.dump(final_hyper_list, f, indent=2)

    # --- Step 6: Needle Probe Scan (Width=1) ---
    # User requested Width=1 with previous ink params.
    candidates_needle = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # NEEDLE Thresholds
        probe_width=1,  # Single pixel scan
        ink_threshold=180,  # Keep as per UserParams
        min_ratio=0.50,
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=1.2,
        scan_rightmost_min_ratio=0.50,
        # Source
        band_source="row_stats",
    )

    # Combine
    final_needle = set(existing_boxes)
    for c in candidates_needle:
        final_needle.add(c)

    final_needle_list = sorted(list(final_needle))

    # Save Needle
    out_needle = run_dir / "expanded_candidates_needle.json"
    with open(out_needle, "w") as f:
        json.dump(final_needle_list, f, indent=2)

    # --- Step 7: No Peak Condition (User Request) ---
    # Disabling peak sharpness check entirely.
    candidates_nopeak = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # NO PEAK Thresholds (Ultraloose base)
        probe_width=4,
        ink_threshold=200,
        min_ratio=0.50,
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=0.0,  # DISABLED (Accept any local max)
        scan_rightmost_min_ratio=0.10,  # Very loose
        max_per_band=0,  # DISABLED limit (Default 8) to catch all peaks
        # Source
        band_source="row_stats",
    )

    # Combine
    final_nopeak = set(existing_boxes)
    for c in candidates_nopeak:
        final_nopeak.add(c)

    final_nopeak_list = sorted(list(final_nopeak))

    # Save NoPeak
    out_nopeak = run_dir / "expanded_candidates_nopeak.json"
    with open(out_nopeak, "w") as f:
        json.dump(final_nopeak_list, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--logs-root",
        required=True,
        help="Root directory containing run dirs (e.g. logs/hybrid_generalization)",
    )
    parser.add_argument("--image-root", required=True, help="Root directory for images")
    parser.add_argument("--run-prefix", default="eval2", help="Process runs starting with this")
    args = parser.parse_args()

    root = Path(args.logs_root)
    run_dirs = [d for d in root.iterdir() if d.is_dir() and d.name.startswith(args.run_prefix)]

    print(f"Found {len(run_dirs)} runs.")

    for run_dir in tqdm(run_dirs):
        process_page(run_dir, Path(args.image_root))


if __name__ == "__main__":
    main()
