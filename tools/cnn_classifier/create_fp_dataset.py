
import argparse
import json
import cv2
import numpy as np
from pathlib import Path
import sys
import os
import shutil

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[2] # tools/cnn_classifier/create_...
sys.path.append(str(REPO_ROOT))

# Attempt to import greedy_barline_match
try:
    from src.common.barline_evaluation import greedy_barline_match
except ImportError:
    # Try alternate relative path if REPO_ROOT logic fails
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from src.common.barline_evaluation import greedy_barline_match

def find_gt_file(gt_root, subdir, page_name):
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists():
        base_dir = Path(gt_root) / page_name
    
    if not base_dir.exists(): return None
    
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
    parser.add_argument("--output-dataset", required=True)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print(f"Scanning {args.scored_root} for FPs...")
    scored_files = []
    for root, dirs, files in os.walk(args.scored_root):
        for file in files:
            if file.endswith("_scored.json"):
                scored_files.append(Path(root) / file)

    out_root = Path(args.output_dataset)
    labels_root = out_root / "labels"
    images_root = out_root / "images"
    labels_root.mkdir(parents=True, exist_ok=True)
    images_root.mkdir(parents=True, exist_ok=True)
    
    fp_count = 0
    
    for json_path in scored_files:
        run_id = json_path.parent.name
        parts = run_id.split('_')
        
        try:
            page_idx = parts.index("page")
            subdir = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])
        except ValueError:
            continue
            
        with open(json_path) as f:
            candidates = json.load(f)
            
        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        if not gt_path: continue
            
        with open(gt_path) as f:
            gt_data = json.load(f)
            
        gt_boxes = []
        for item in gt_data:
            if isinstance(item, list): gt_boxes.append(tuple(item[:4]))
            elif isinstance(item, dict):
                if "box" in item: gt_boxes.append(tuple(item["box"]))
                elif "barline_location" in item: gt_boxes.append(tuple(item["barline_location"]))

        accepted_candidates = [c for c in candidates if c["score"] > args.threshold]
        accepted_boxes = [tuple(c["bbox"]) for c in accepted_candidates]
        
        match_result = greedy_barline_match(accepted_boxes, gt_boxes)
        
        if not match_result.false_positive_indices:
            continue

        # Load Image
        img_path = Path(args.image_root) / subdir / f"{page_name}.png"
        if not img_path.exists():
             rev_alias = {"prokofiev1": "Va_Prokofiev_Symphony1"}
             real_subdir = rev_alias.get(subdir, subdir)
             img_path = Path(args.image_root) / real_subdir / f"{page_name}.png"
             
        if not img_path.exists(): continue
            
        img = cv2.imread(str(img_path))
        if img is None: continue
        
        # Save FPs
        for idx in match_result.false_positive_indices:
            box = accepted_boxes[idx]
            x1, y1, x2, y2 = map(int, box)
            
            # Crop 
            # We want slightly context?
            # CNN training used crops from boxes directly, sometimes with padding.
            # Here we just save the crop of the box itself or maybe context?
            # Standard training usually centers on the box.
            # Let's save the box crop and label 0.
            # Wait, cnn_barline_classification loads by box from full image usually?
            # Or dataset is pre-cropped?
            # Usually pre-cropped images in `images/0` and `images/1`.
            
            # Let's create `images/0` (negative) structure.
            neg_dir = out_root / "0"
            neg_dir.mkdir(exist_ok=True)
            
            # Crop exactly the bbox? Or with some padding?
            # The detector output is the candidate box.
            # Let's crop exactly.
            crop = img[y1:y2, x1:x2]
            
            if crop.size == 0: continue
            
            filename = f"fp_{subdir}_{page_name}_{x1}_{y1}.png"
            cv2.imwrite(str(neg_dir / filename), crop)
            fp_count += 1
            
            if args.limit and fp_count >= args.limit:
                break
        if args.limit and fp_count >= args.limit:
            break

    print(f"Extracted {fp_count} FP samples to {out_root}")

if __name__ == "__main__":
    main()
