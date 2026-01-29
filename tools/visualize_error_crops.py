import argparse
import json
import os
import sys
from pathlib import Path

import cv2

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match


def find_gt_file(gt_root, subdir, page_name):
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists():
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
    parser.add_argument(
        "--padding", type=int, default=100, help="Padding around error box for crop"
    )
    args = parser.parse_args()

    print(f"DEBUG: Searching in {args.scored_root}...")
    scored_files = []
    for root, dirs, files in os.walk(args.scored_root):
        for file in files:
            if file.endswith("_scored.json"):
                scored_files.append(Path(root) / file)

    print(f"Found {len(scored_files)} scored files")

    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for json_path in scored_files:
        run_id = json_path.parent.name
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

        with open(json_path) as f:
            candidates = json.load(f)

        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        if not gt_path:
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

        match_result = greedy_barline_match(accepted_candidates, gt_boxes)

        has_fp = len(match_result.false_positive_indices) > 0
        has_fn = len(match_result.false_negative_indices) > 0

        if not has_fp and not has_fn:
            continue

        # Load Image
        img_path = Path(args.image_root) / subdir / f"{page_name}.png"
        if not img_path.exists():
            rev_alias = {"prokofiev1": "Va_Prokofiev_Symphony1"}
            real_subdir = rev_alias.get(subdir, subdir)
            img_path = Path(args.image_root) / real_subdir / f"{page_name}.png"

        if not img_path.exists():
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        H, W = img.shape[:2]

        # Generate Crops for FPS
        for idx in match_result.false_positive_indices:
            box = accepted_candidates[idx]  # Predicted box
            x1, y1, x2, y2 = map(int, box)

            # Crop bounds
            cx1 = max(0, x1 - args.padding)
            cy1 = max(0, y1 - args.padding)
            cx2 = min(W, x2 + args.padding)
            cy2 = min(H, y2 + args.padding)

            crop = img[cy1:cy2, cx1:cx2].copy()

            # Draw box relative to crop
            bx1, by1 = x1 - cx1, y1 - cy1
            bx2, by2 = x2 - cx1, y2 - cy1

            # Draw THICK distinct box
            # FP = Red, Thick
            cv2.rectangle(crop, (bx1, by1), (bx2, by2), (0, 0, 255), 4)

            out_name = f"{subdir}_{page_name}_FP_{x1}_{y1}.png"
            cv2.imwrite(str(out_root / out_name), crop)
            print(f"Saved FP crop: {out_name}")

        # Generate Crops for FNs
        for idx in match_result.false_negative_indices:
            box = gt_boxes[idx]  # GT box
            x1, y1, x2, y2 = map(int, box)

            # Crop bounds
            cx1 = max(0, x1 - args.padding)
            cy1 = max(0, y1 - args.padding)
            cx2 = min(W, x2 + args.padding)
            cy2 = min(H, y2 + args.padding)

            crop = img[cy1:cy2, cx1:cx2].copy()

            # Draw box relative to crop
            bx1, by1 = x1 - cx1, y1 - cy1
            bx2, by2 = x2 - cx1, y2 - cy1

            # Draw THICK distinct box
            # FN = Magenta (255, 0, 255), Thick
            # Also draw an inner thin line of a different color to ensure visibility against any background?
            # Let's just do thick Magenta.
            cv2.rectangle(crop, (bx1, by1), (bx2, by2), (255, 0, 255), 4)

            out_name = f"{subdir}_{page_name}_FN_{x1}_{y1}.png"
            cv2.imwrite(str(out_root / out_name), crop)
            print(f"Saved FN crop: {out_name}")


if __name__ == "__main__":
    main()
