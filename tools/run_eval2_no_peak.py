import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan, load_preds


def process_run(run_dir: Path, img_root: Path):
    run_id = run_dir.name
    # Parse run_id: eval2_<pdf_stem>_<page_name>
    parts = run_id.split("_")
    try:
        page_idx = parts.index("page")
        pdf_stem = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])
        img_path = img_root / pdf_stem / f"{page_name}.png"
    except ValueError:
        print(f"Skipping {run_id}: format unknown")
        return

    if not img_path.exists():
        print(f"Skipping {run_id}: Image not found {img_path}")
        return

    img = cv2.imread(str(img_path))
    if img is None:
        return

    hybrid_json = run_dir / "hybrid_predictions.json"
    if not hybrid_json.exists():
        print(f"Skipping {run_id}: No hybrid_predictions.json")
        return

    existing_boxes = load_preds(hybrid_json)

    # Staff mask not needed for row_stats
    staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)

    # --- No Peak Probe Scan ---
    # Parameters from "No Peak" Experiment (Exp 7.3)
    # Effectively disabling peak sharpness and count limits.
    candidates = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        band_source="row_stats",
        # Rescue enabled
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # Standard Width/Ink
        probe_width=4,
        ink_threshold=210,
        # No Peak Parameters
        scan_x_peak_ratio_min=0.0,  # Disable peak sharpness check
        scan_rightmost_min_ratio=0.0,  # Disable rightmost sharpness check
        max_per_band=100,  # Increase limit
        # Consistent with standard scan
        min_ratio=0.85,  # Keep basic ratio check? Or was this also disabled?
        # User said "effectively disabling peak sharpness".
        # Assuming min_ratio (darkness) is still needed to detect "candidate".
        # If I disable min_ratio, I get everything.
        # I'll keep 0.85 unless "No Peak" meant "All Thresholds Low".
        # Exp 7.3 log says "recall jumped".
        # I'll stick to 0.85 for consistency with baseline, only removing Peak check.
        # Wait, if Peak check was the bottleneck (FN diagnosis), then removing it helps.
        scan_center_on_peak=True,
    )

    # Combine
    final_set = set(existing_boxes)
    for c in candidates:
        final_set.add(c)

    final_list = sorted(list(final_set))

    # Save
    out_path = run_dir / "pipeline2_no_peak_candidates.json"
    with open(out_path, "w") as f:
        json.dump(final_list, f, indent=2)

    print(f"Processed NoPeak {run_id}: {len(existing_boxes)} -> {len(final_list)}")


def main():
    log_root = Path("logs/hybrid_generalization")
    img_root = Path("data/evaluation2/images")

    for run_dir in sorted(log_root.glob("eval2_*")):
        process_run(run_dir, img_root)


if __name__ == "__main__":
    main()
