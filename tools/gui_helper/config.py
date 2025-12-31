import os

# =============================================================================
# GUI Helper Configuration
# =============================================================================
# This file contains the paths to the data we want to inspect.
# Change these paths when you want to load a different page or run.

# Base directory of the repo (one level up from tools/gui_helper/)
# logic: tools/gui_helper/config.py -> ../../ -> repo_root
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))

# Path to the JSON file containing the detected barlines (predictions).
# We are using the 'detections.json' which has the 'pred_bbox' fields.
# Updated to point to the latest stable run (Heuristic 1 Final).
METRICS_PATH = os.path.join(
    BASE_DIR,
    "logs/homr_eval/20251206T_homr_heuristic_final/page_3/page_3_detections.json"
)

# Path to the corresponding score image (page 3).
# We will serve this image dynamically via Flask.
# Note: The image name in the log dir might be different or same, checking logic:
# usually it is copied there.
IMAGE_PATH = os.path.join(
    BASE_DIR,
    "logs/homr_eval/20251206T_homr_heuristic_final/page_3/page_3.png"
)

# Scan debug JSON (from run_gt_rebuild_hybrid_eval.py --endbar-debug).
SCAN_PATH = os.path.join(
    BASE_DIR,
    "logs/gt_rebuild_hybrid_eval/20251231T154529_probe_ext_tb0p35_rowstats_hscan_padR0p50_lr0p60_ml5_debug_rowband_profile/per_page/page_001/endbar_debug.json"
)

# Optional image path for scan GUI. Defaults to IMAGE_PATH if not set.
SCAN_IMAGE_PATH = os.path.join(
    BASE_DIR,
    "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
)

# Directory to save the manual feedback (JSON).
OUTPUT_DIR = os.path.join(
    os.path.dirname(METRICS_PATH) # Save alongside the input file
)

# File to store the manually ignored barline IDs.
# This file will be created by the save functionality.
# It is safe to delete this file if you want to reset the manual decisions.
MANUAL_IGNORE_PATH = os.path.join(OUTPUT_DIR, "manual_ignore.json")
