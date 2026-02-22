import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import find_peaks


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_image_path(json_path, image_root):
    # json_path: data/evaluation2/annotations/subdir/page_xxx/boxes.json
    # image_path: data/evaluation2/images/subdir/page_xxx.png
    parts = Path(json_path).parts
    # parts: ('data', 'evaluation2', 'annotations', 'subdir', 'page_xxx', 'boxes.json')
    # We assume standard structure
    if "annotations" in parts:
        idx = parts.index("annotations")
        subdir = parts[idx + 1]
        page_dir = parts[idx + 2]
        # page_dir is likely 'page_001', so we need 'page_001.png'
        # Check if page_dir is actually a directory or part of filename?
        # The glob in find showed .../subdir/page_004/boxes_sorted_v...json
        # So page_dir is 'page_004'.
        image_name = page_dir + ".png"
        image_path = Path(image_root) / subdir / image_name
        return str(image_path)
    return None


def extract_peaks(crop):
    # crop is (H, W) or (H, W, C)
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Invert (Ink is dark (low value), Background is light (high value))
    # Standard images: White=255, Black=0.
    # We want peaks for Black. So Invert: 255 - pixel.
    inverted = 255 - gray

    # Sum along Y axis (collapse height) to get X profile
    profile = np.sum(inverted, axis=0)

    # Normalize profile
    if np.max(profile) > 0:
        profile = profile / np.max(profile)

    # Find peaks
    # distance=3: peaks must be at least 3 pixels apart
    # prominence=0.2: peaks must be somewhat distinct
    peaks, properties = find_peaks(profile, distance=3, prominence=0.1)

    return peaks, profile


def visualize_split(image, original_box, split_boxes, output_path, peaks=None, profile=None):
    # Create a visual debug image
    x1, y1, x2, y2 = original_box

    # Crop with padding for context
    pad = 20
    h, w = image.shape[:2]
    cx1 = max(0, x1 - pad)
    cy1 = max(0, y1 - pad)
    cx2 = min(w, x2 + pad)
    cy2 = min(h, y2 + pad)

    crop = image[cy1:cy2, cx1:cx2].copy()

    # Draw original box (Red) in crop coords
    cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), 2)

    # Draw new boxes (Green)
    for box in split_boxes:
        bx1, by1, bx2, by2 = box
        cv2.rectangle(crop, (bx1 - cx1, by1 - cy1), (bx2 - cx1, by2 - cy1), (0, 255, 0), 2)

    cv2.imwrite(output_path, crop)


def _extract_bbox(record):
    if isinstance(record, list) and len(record) == 4:
        return [int(v) for v in record], False
    if isinstance(record, dict):
        bbox = record.get("barline_location") or record.get("bbox") or record.get("pred_bbox")
        if bbox and len(bbox) == 4:
            return [int(v) for v in bbox], True
    return None, False


def _should_split(record, bbox, min_split_width):
    x1, y1, x2, y2 = bbox
    width = abs(x2 - x1)
    if width < min_split_width:
        return False
    if isinstance(record, dict):
        bar_type = record.get("barline_type", "barline")
        if bar_type in {"double_barline", "end_barline", "repeat"}:
            return True
    return True


def process_file(json_path, image_root, output_vis_dir, dry_run=True, min_split_width=12):
    data = load_json(json_path)
    image_path = get_image_path(json_path, image_root)

    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return 0, []

    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load image: {image_path}")
        return 0, []

    changes = []

    # We assume 'data' is a list of dicts (GT format)
    # Check format
    if isinstance(data, dict) and "predictions" in data:
        # Standard hybrid output format, but GT is usually a list
        records = data["predictions"]
    elif isinstance(data, list):
        records = data
    else:
        print(f"Unknown JSON format in {json_path}")
        return 0, []

    modified_count = 0

    # First pass: Check if we have overlapping single lines for double bars
    # But for "Lumped Only", we expect only the double_barline box.
    # The simple approach: If type is double_barline, try to split it.

    final_records = []

    for idx, record in enumerate(records):
        bbox, is_dict = _extract_bbox(record)
        if not bbox:
            final_records.append(record)
            continue

        if _should_split(record, bbox, min_split_width):
            x1, y1, x2, y2 = bbox

            # Extract crop
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                final_records.append(record)
                continue

            peaks, profile = extract_peaks(crop)

            if len(peaks) == 2:
                # Successfully found 2 peaks
                modified_count += 1

                # Create 2 new records
                for peak_x in peaks:
                    # Peak X is relative to x1
                    # New box width? Standard barline is usually 4-6px?
                    # Or just take +/- 2px around peak?
                    center_x = x1 + peak_x
                    new_w = 4  # 4px width
                    nx1 = int(center_x - new_w // 2)
                    nx2 = int(center_x + new_w // 2)

                    # Ensure within original Y range, and reasonable X
                    nx1 = max(0, nx1)
                    nx2 = min(image.shape[1], nx2)

                    if is_dict:
                        new_record = record.copy()
                        # Keep original label for consistency with GT policy.
                        new_record["barline_location"] = [nx1, y1, nx2, y2]
                        if "bbox" in new_record:
                            new_record["bbox"] = [nx1, y1, nx2, y2]
                        final_records.append(new_record)
                    else:
                        final_records.append([nx1, y1, nx2, y2])

                # Visualization
                vis_name = f"{Path(json_path).parent.name}_{Path(json_path).name.replace('.json', '')}_idx{idx}.png"
                vis_path = os.path.join(output_vis_dir, vis_name)

                # Prepare split boxes for vis
                split_boxes = []
                for peak_x in peaks:
                    center_x = x1 + peak_x
                    new_w = 4
                    nx1 = int(center_x - new_w // 2)
                    nx2 = int(center_x + new_w // 2)
                    split_boxes.append([nx1, y1, nx2, y2])

                visualize_split(image, [x1, y1, x2, y2], split_boxes, vis_path)

            else:
                # Failed to find exactly two peaks; keep original.
                final_records.append(record)
        else:
            final_records.append(record)

    if modified_count > 0 and not dry_run:
        save_json(final_records, json_path)

    return modified_count, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json-root", required=True, help="Root of annotations (e.g. data/evaluation2/annotations)"
    )
    parser.add_argument(
        "--image-root", required=True, help="Root of images (e.g. data/evaluation2/images)"
    )
    parser.add_argument(
        "--output-vis", default="logs/double_barline_vis", help="Directory to save visualizations"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes to JSON files (default: dry-run)"
    )
    parser.add_argument(
        "--file-pattern",
        default="boxes_provisional.json",
        help="Target JSON filename to process (default: boxes_provisional.json)",
    )
    parser.add_argument(
        "--min-split-width",
        type=int,
        default=12,
        help="Minimum bbox width in px to try splitting (default: 12)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_vis, exist_ok=True)

    # Find target files
    json_files = []
    for root, dirs, files in os.walk(args.json_root):
        for file in files:
            if file == args.file_pattern:
                json_files.append(os.path.join(root, file))

    total_modified = 0
    for json_file in json_files:
        # Filter for double_barline existence first to be fast?
        # Or just let process_file handle it.
        # process_file loads the json anyway.

        print(f"Processing {json_file}...")
        count, _ = process_file(
            json_file,
            args.image_root,
            args.output_vis,
            dry_run=not args.apply,
            min_split_width=args.min_split_width,
        )
        total_modified += count

    print(f"Total double barlines split: {total_modified}")
    if not args.apply:
        print("Dry run completed. Use --apply to save changes.")


if __name__ == "__main__":
    main()
