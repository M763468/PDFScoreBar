import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Import logic from run_gt_rebuild_hybrid_eval
# Note: These imports assume run_gt_rebuild_hybrid_eval is accessible as a module or in path.
# Since it's a script in tools/, we import it via tools.run_gt_rebuild_hybrid_eval

# Import logic from run_gt_rebuild_hybrid_eval
# Note: These imports assume run_gt_rebuild_hybrid_eval is accessible as a module or in path.
# Since it's a script in tools/, we import it via tools.run_gt_rebuild_hybrid_eval
from tools.run_gt_rebuild_hybrid_eval import (
    dilate_mask,
    geom_notehead_ratio_filter,
    load_preds,
    median_barline_height,
    row_filter,
)

# Constants (matching Phase 6 params)
PROBE_ROW_MAX_DIST = 15.0
PROBE_ROW_MIN_COUNT = 3
PROBE_ROW_TOL_TOP = 20.0
PROBE_ROW_TOL_BOTTOM = 20.0

NOTEHEAD_FILTER_PARAMS = {
    "endpoint_ratio_threshold": 0.4,
    "probe_endpoint_x_scale": 1.0,
    "probe_endpoint_y_scale": 0.75,
    "endpoint_scale_base": "height",
    "probe_notehead_dilate": 5,
    "notehead_min_area": 15,
}


def load_mask(path, shape):
    if not path.exists():
        return np.zeros(shape, dtype=np.uint8)
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(shape, dtype=np.uint8)
    if img.shape != shape:
        img = cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return img


def process_run(run_dir: Path, img_root: Path):
    run_id = run_dir.name
    # Parse run_id: eval2_<pdf_stem>_<page_name>
    parts = run_id.split("_")
    try:
        page_idx = parts.index("page")
        pdf_stem = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])
        # Image path
        img_path = img_root / pdf_stem / f"{page_name}.png"
    except ValueError:
        print(f"Skipping {run_id}: format unknown")
        return

    if not img_path.exists():
        print(f"Skipping {run_id}: Image not found {img_path}")
        return

    # Load Image
    img = cv2.imread(str(img_path))
    if img is None:
        return

    # Load Hybrid Preds (Baseline)
    hybrid_json = run_dir / "hybrid_predictions.json"
    if not hybrid_json.exists():
        print(f"Skipping {run_id}: No hybrid_predictions.json")
        return

    candidates = load_preds(hybrid_json)

    # --- Filter 1: Row Filter ---
    # We don't have row_stats unless we build them.
    # row_filter simple version takes candidates and groups them.
    # Definition: row_filter(preds, cluster_max_dist, min_row_count, tol_top, tol_bottom)
    row_filtered = row_filter(
        candidates,
        cluster_max_dist=PROBE_ROW_MAX_DIST,
        min_row_count=PROBE_ROW_MIN_COUNT,
        tol_top=PROBE_ROW_TOL_TOP,
        tol_bottom=PROBE_ROW_TOL_BOTTOM,
    )

    # --- Filter 2: Notehead Filter ---
    # Requires masks from homr output
    # Homr output: output_root/baseline/<page_name>/
    # Actually run_hybrid_pipeline.sh: output_root/baseline/<run_id>/<page_name>_debug_...
    # run_id is STEM ("page_XXX") in run_hybrid_pipeline.sh Step 1.
    homr_dir = run_dir / "baseline" / page_name
    notehead_mask_path = homr_dir / f"{page_name}_debug_6_notehead.png"

    notehead_mask = load_mask(notehead_mask_path, img.shape[:2])

    probe_notehead_mask = dilate_mask(
        notehead_mask, NOTEHEAD_FILTER_PARAMS["probe_notehead_dilate"]
    )

    barline_height = median_barline_height(row_filtered)

    # Definition: geom_notehead_ratio_filter(preds, notehead_mask, staff_space_px, threshold, endpoint_x_scale, endpoint_y_scale, *, endpoint_scale_base, barline_height_px)
    geom_kept, debug_info = geom_notehead_ratio_filter(
        row_filtered,
        probe_notehead_mask,
        staff_space_px=20.0,  # Estimation is hard without analysis, typically ~20px for 300dpi?
        threshold=NOTEHEAD_FILTER_PARAMS["endpoint_ratio_threshold"],
        endpoint_x_scale=NOTEHEAD_FILTER_PARAMS["probe_endpoint_x_scale"],
        endpoint_y_scale=NOTEHEAD_FILTER_PARAMS["probe_endpoint_y_scale"],
        endpoint_scale_base=NOTEHEAD_FILTER_PARAMS["endpoint_scale_base"],  # "height" from config
        barline_height_px=barline_height,
    )

    # Save Results
    out_path = run_dir / "pipeline1_baseline_filtered.json"
    with open(out_path, "w") as f:
        json.dump(geom_kept, f, indent=2)

    print(f"Processed {run_id}: {len(candidates)} -> {len(row_filtered)} -> {len(geom_kept)}")


def main():
    log_root = Path("logs/hybrid_generalization")
    img_root = Path("data/evaluation2/images")

    for run_dir in sorted(log_root.glob("eval2_*")):
        process_run(run_dir, img_root)


if __name__ == "__main__":
    main()
