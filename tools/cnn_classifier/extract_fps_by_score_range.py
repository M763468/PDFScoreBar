#!/usr/bin/env python3
"""
Extract False Positive crops by CNN score range for active learning.

This script extracts FP image crops from scored evaluation results,
filtering by CNN confidence score to select the most informative samples
for retraining.
"""

import argparse
import json
from pathlib import Path
from typing import List

import cv2
import numpy as np
from tqdm import tqdm


def extract_crop(image_path: Path, box: List[int], size: int = 256) -> np.ndarray:
    """Extract a square crop centered on the bounding box."""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    half = size // 2
    crop_x1 = max(0, cx - half)
    crop_y1 = max(0, cy - half)
    crop_x2 = min(img.shape[1], cx + half)
    crop_y2 = min(img.shape[0], cy + half)

    crop = img[crop_y1:crop_y2, crop_x1:crop_x2]

    # Pad if necessary
    if crop.shape[0] < size or crop.shape[1] < size:
        padded = np.full((size, size), 255, dtype=np.uint8)
        y_offset = (size - crop.shape[0]) // 2
        x_offset = (size - crop.shape[1]) // 2
        padded[y_offset : y_offset + crop.shape[0], x_offset : x_offset + crop.shape[1]] = crop
        crop = padded

    return crop


def find_image_for_scored_file(scored_path: Path, image_root: Path) -> Path:
    """Find the corresponding image file for a scored JSON."""
    # Parse run_id from parent directory name
    run_id = scored_path.parent.name  # e.g., eval2_prokofiev5_page_001
    parts = run_id.split("_")

    # Find 'page' index
    try:
        page_idx = parts.index("page")
        score_name = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])  # page_001
    except ValueError:
        raise ValueError(f"Cannot parse run_id: {run_id}")

    # Try to find image
    image_path = image_root / score_name / f"{page_name}.png"
    if not image_path.exists():
        # Try recursive search
        found = list(image_root.rglob(f"{page_name}.png"))
        if found:
            for f in found:
                if score_name in str(f):
                    image_path = f
                    break
            else:
                image_path = found[0]

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found for {run_id}: {image_path}")

    return image_path


def main():
    parser = argparse.ArgumentParser(description="Extract FP crops by score range")
    parser.add_argument("--scored-root", required=True, help="Root directory with scored JSONs")
    parser.add_argument("--image-root", required=True, help="Root directory with images")
    parser.add_argument("--gt-root", required=True, help="Root directory with GT annotations")
    parser.add_argument("--output-dir", required=True, help="Output directory for FP crops")
    parser.add_argument("--min-score", type=float, default=0.5, help="Minimum CNN score")
    parser.add_argument("--max-score", type=float, default=0.9, help="Maximum CNN score")
    parser.add_argument("--max-samples", type=int, default=2000, help="Maximum samples to extract")
    parser.add_argument("--threshold", type=float, default=0.5, help="Detection threshold")
    args = parser.parse_args()

    scored_root = Path(args.scored_root)
    image_root = Path(args.image_root)
    gt_root = Path(args.gt_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all scored files
    scored_files = list(scored_root.rglob("*_scored.json"))
    print(f"Found {len(scored_files)} scored files")

    fp_candidates = []

    # Collect FP candidates with scores in range
    for scored_path in tqdm(scored_files, desc="Scanning for FPs"):
        try:
            # Load scored results
            with open(scored_path) as f:
                scored_data = json.load(f)

            # Parse run_id
            run_id = scored_path.parent.name
            parts = run_id.split("_")
            page_idx = parts.index("page")
            score_name = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])

            # Load GT
            gt_path = gt_root / score_name / page_name / "boxes_sorted_v20260111.json"
            if not gt_path.exists():
                gt_path = gt_root / score_name / page_name / "boxes_sorted.json"
            if not gt_path.exists():
                continue

            with open(gt_path) as f:
                gt_data = json.load(f)
            gt_boxes = [item["barline_location"] for item in gt_data]

            # Find image
            image_path = find_image_for_scored_file(scored_path, image_root)

            # Check each detection
            for item in scored_data:
                score = item.get("score", 0.0)  # Changed from cnn_score
                box = item.get("bbox", item.get("box"))  # Support both formats

                if box is None:
                    continue

                # Filter by score range
                if not (args.min_score <= score <= args.max_score):
                    continue

                # Check if it's a FP (not matching any GT)
                is_fp = True
                x1, y1, x2, y2 = box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                for gt_box in gt_boxes:
                    gx1, gy1, gx2, gy2 = gt_box
                    gcx = (gx1 + gx2) / 2
                    gcy = (gy1 + gy2) / 2

                    if abs(cx - gcx) < 10 and abs(cy - gcy) < 50:
                        is_fp = False
                        break

                if is_fp and score >= args.threshold:
                    fp_candidates.append(
                        {"image_path": image_path, "box": box, "score": score, "run_id": run_id}
                    )

        except Exception as e:
            print(f"Error processing {scored_path}: {e}")
            continue

    print(
        f"\nFound {len(fp_candidates)} FP candidates in score range [{args.min_score}, {args.max_score}]"
    )

    # Sort by score (descending) and take top N
    fp_candidates.sort(key=lambda x: x["score"], reverse=True)
    fp_candidates = fp_candidates[: args.max_samples]

    print(f"Extracting {len(fp_candidates)} FP crops...")

    # Extract crops
    for i, fp in enumerate(tqdm(fp_candidates, desc="Extracting crops")):
        try:
            crop = extract_crop(fp["image_path"], fp["box"])
            output_path = output_dir / f"fp_{i:05d}_score{fp['score']:.3f}_{fp['run_id']}.png"
            cv2.imwrite(str(output_path), crop)
        except Exception as e:
            print(f"Error extracting crop {i}: {e}")
            continue

    print(f"\nExtracted {len(list(output_dir.glob('*.png')))} FP crops to {output_dir}")
    print(f"Score range: [{args.min_score}, {args.max_score}]")


if __name__ == "__main__":
    main()
