import argparse
import json
import os
import sys
from pathlib import Path

import cv2

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Attempt to import greedy_barline_match
try:
    from src.common.barline_evaluation import greedy_barline_match
except ImportError:
    print("Failed to import greedy_barline_match")
    sys.exit(1)


def find_gt_file(gt_root, subdir, page_name):
    # Standard: gt_root/Score/Page/boxes_sorted.json
    # Or: gt_root/Page/boxes_sorted.json (old structure)

    # Try Score/Page structure first
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists():
        # Fallback to just Page if no subdir
        base_dir = Path(gt_root) / page_name

    if not base_dir.exists():
        return None

    candidates = list(base_dir.glob("boxes_sorted*.json"))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-root", required=True)
    parser.add_argument("--scored-root", required=True)
    parser.add_argument("--gt-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    print(f"DEBUG: Searching in {args.scored_root}...")
    scored_files = []
    for root, dirs, files in os.walk(args.scored_root):
        for file in files:
            if file.endswith("_scored.json"):
                scored_files.append(Path(root) / file)
                # print(f"DEBUG: Found {file}")

    print(f"Found {len(scored_files)} scored files")

    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for json_path in scored_files:
        print(f"Processing candidate: {json_path}")
        run_id = json_path.parent.name  # Use directory name as run_id!
        # Filename is usually pipeline2_no_peak_scored.json, so stem logic fails if we use filename.
        # run_id logic in previous code: json_path.stem.replace(...)
        # json_path.stem = pipeline2_no_peak_scored
        # run_id becomes pipeline2_no_peak.
        # parts = ['pipeline2', 'no', 'peak'].
        # "page" is NOT in parts.
        # Logic fails!

        # FIX: Derive run_id from PARENT DIRECTORY.
        # Expect directory: eval2_ScoreName_page_XXX

        parts = run_id.split("_")

        try:
            page_idx = -1
            for i, p in enumerate(parts):
                if p == "page":
                    page_idx = i
                    break
            if page_idx == -1:
                continue
            subdir = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])
        except Exception:
            continue

        # Load Candidates
        with open(json_path) as f:
            candidates = json.load(f)

        # Load GT
        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        if not gt_path:
            print(f"GT not found for {subdir}/{page_name}")
            continue

        with open(gt_path) as f:
            gt_data = json.load(f)

        gt_boxes = []
        for item in gt_data:
            if isinstance(item, list):
                gt_boxes.append(tuple(item[:4]))
            elif isinstance(item, dict):
                if "box" in item:
                    gt_boxes.append(tuple(item["box"]))
                elif "barline_location" in item:
                    gt_boxes.append(tuple(item["barline_location"]))

        accepted_candidates = [tuple(c["bbox"]) for c in candidates if c["score"] > args.threshold]

        # Match
        match_result = greedy_barline_match(accepted_candidates, gt_boxes)
        # Matches = TP (Green)
        # FP indices = FP (Red)
        # FN indices = FN (Blue)

        if not match_result.false_positive_indices and not match_result.false_negative_indices:
            # Skip perfect pages to save space/time? Or visualize all?
            # User asked to visualize remaining FP/FN. So verify perfect ones too?
            # Let's verify all for now.
            pass

        # Load Image
        # Image path: image_root/subdir/page_name.png
        # Check alias again?
        # Image filenames in run_eval_experiment were inferred from folder...
        # So subdir should match folder name.

        img_path = Path(args.image_root) / subdir / f"{page_name}.png"
        if not img_path.exists():
            # Try flat if subdir doesn't exact match
            # Alias map check?
            # Reverse alias: prokofiev1 -> Va_Prokofiev_Symphony1
            rev_alias = {"prokofiev1": "Va_Prokofiev_Symphony1"}
            real_subdir = rev_alias.get(subdir, subdir)
            img_path = Path(args.image_root) / real_subdir / f"{page_name}.png"

        if not img_path.exists():
            print(f"Image not found: {img_path}")
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        # Draw
        # TP: Green (0, 255, 0) - Thinner
        for m in match_result.matches:
            b = accepted_candidates[m.pred_index]
            cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 2)

        # FP: Red (0, 0, 255) - Thicker
        for idx in match_result.false_positive_indices:
            b = accepted_candidates[idx]
            cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 0, 255), 2)

        # FN: Blue (255, 0, 0) - Thicker, use GT box
        for idx in match_result.false_negative_indices:
            b = gt_boxes[idx]
            cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (255, 0, 0), 2)

        # Save
        out_name = f"{subdir}_{page_name}_vis.png"
        cv2.imwrite(str(out_root / out_name), img)
        print(f"Saved visualization: {out_name}")


if __name__ == "__main__":
    main()
