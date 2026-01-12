
import argparse
import json
import sys
import cv2
import numpy as np
from pathlib import Path

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Import logic (assuming these are available in PYTHONPATH or via relative import)
# If direct import fails, we might need to adjust sys.path more carefully
try:
    from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan, load_preds
except ImportError:
    # Fallback to src imports if available, or try to find where detect_probe_scan is
    # Based on previous context, it is in tools/run_gt_rebuild_hybrid_eval.py
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ink-threshold", type=int, default=210)
    parser.add_argument("--min-ratio", type=float, default=0.85)
    parser.add_argument("--pattern", type=str, default="*.png")
    parser.add_argument("--score-name", type=str, default=None, help="e.g. Va_Prokofiev_Symphony1. If None, inferred from image parent dir.")
    parser.add_argument("--bands-from", type=Path, default=None, help="JSON file OR directory root with existing boxes to define bands")
    parser.add_argument("--band-min-row-count", type=int, default=1)
    parser.add_argument("--min-height-ratio", type=float, default=0.012, help="Minimum height ratio (relative to image height) of candidate to keep")
    parser.add_argument("--vertical-closing", type=int, default=0)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    
    # Pre-load bands if a specific file is provided, otherwise we load per image
    global_bands = []
    bands_is_dir = False
    if args.bands_from:
        if args.bands_from.is_file():
            with open(args.bands_from) as f:
                data = json.load(f)
                for item in data:
                    if isinstance(item, dict) and "bbox" in item:
                        global_bands.append(tuple(item["bbox"]))
                    elif isinstance(item, list) and len(item) == 4:
                        global_bands.append(tuple(item))
            print(f"Loaded {len(global_bands)} global existing boxes")
        elif args.bands_from.is_dir():
            bands_is_dir = True
            print(f"Will resolve bands from directory: {args.bands_from}")

    images = list(args.image_root.glob(args.pattern))
    print(f"Found {len(images)} images in {args.image_root}")

    for img_path in images:
        stem = img_path.stem # e.g. page_002
        
        # Infer score name if not provided
        current_score_name = args.score_name if args.score_name else img_path.parent.name
        # Construction run_id and resolve baseline path
        baseline_score_name = current_score_name
        
        # Construct run_id
        # For output we keep consistent with folder name if possible, or alias?
        # Let's use image folder name for output to be clear.
        run_id = f"eval2_{current_score_name}_{stem}"
        run_dir = args.output_root / run_id
        run_dir.mkdir(exist_ok=True)
        
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Failed to load {img_path}")
            continue

        # Staff mask - dummy for row_stats mode
        staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        
        # Resolve existing boxes
        existing_boxes = []
        if bands_is_dir:
            # Try to find corresponding json file in subdirectory
            # Directory name: eval2_{BaselineScoreName}_{Page}
            # File name: pipeline2_no_peak_scored.json (output of scoring)
            run_subdir = f"eval2_{baseline_score_name}_{stem}"
            cand_path = args.bands_from / run_subdir / "pipeline2_no_peak_scored.json"
            if not cand_path.exists():
                # Fallback to older naming if any
                cand_path = args.bands_from / f"{run_subdir}_scored.json"
                
            if not cand_path.exists():
                print(f"Warning: Baseline candidates not found for {run_id} at {cand_path}")
                # Try recursive search if needed, but strict naming is safer
                pass
            else:
                with open(cand_path) as f:
                    data = json.load(f)
                    for item in data:
                        if isinstance(item, dict) and "bbox" in item:
                            existing_boxes.append(tuple(item["bbox"]))
                        elif isinstance(item, list) and len(item) == 4:
                            existing_boxes.append(tuple(item))
        else:
            existing_boxes = global_bands if global_bands else []

        if not existing_boxes and args.bands_from:
            print(f"Warning: No bands loaded for {run_id}")

        candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            band_source="row_stats",
            band_min_row_count=args.band_min_row_count,
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=args.ink_threshold,
            min_ratio=args.min_ratio,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.0,
            max_per_band=100,
            scan_center_on_peak=True,
            vertical_closing=args.vertical_closing
        )


        img_h = img.shape[0]
        min_height_px = int(img_h * args.min_height_ratio)

        # Filter new candidates
        filtered_candidates = []
        for c in candidates:
            h = abs(c[3] - c[1])
            if h >= min_height_px:
                filtered_candidates.append(c)
                
        # Merge with existing boxes
        # Use set of tuples for dedup
        final_set = set()
        
        # Also apply filter to existing boxes for consistency?
        # Probably yes, noise could exist there too.
        for b in existing_boxes:
            h = abs(b[3] - b[1])
            if h >= min_height_px:
                final_set.add(tuple(b))
            
        for c in filtered_candidates:
            final_set.add(tuple(c))
        
        final_list = sorted(list(final_set))

        # Output format
        out_path = run_dir / "pipeline2_no_peak_candidates.json"
        
        with open(out_path, 'w') as f:
            json.dump(final_list, f, indent=2)
            
        print(f"Processed {stem}: {len(final_list)} candidates (merged)")

if __name__ == "__main__":
    main()
