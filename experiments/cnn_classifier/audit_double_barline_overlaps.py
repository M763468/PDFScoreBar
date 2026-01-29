import argparse
import json
from collections import defaultdict
from pathlib import Path


def calculate_iou(box1, box2):
    # Standard IoU, but we are interested if box2 is INSIDE box1 mostly.
    # box format: [x1, y1, x2, y2]
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)

    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0, 0.0

    inter_area = (inter_x2 - inter_x1 + 1) * (inter_y2 - inter_y1 + 1)
    area1 = (x2_1 - x1_1 + 1) * (y2_1 - y1_1 + 1)
    area2 = (x2_2 - x1_2 + 1) * (y2_2 - y1_2 + 1)

    iou = inter_area / float(area1 + area2 - inter_area)
    containment = inter_area / float(area2)  # How much of box2 is inside box1

    return iou, containment


def audit_file(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return

    # Handle different formats (list vs dict with "predictions")
    if isinstance(data, dict):
        boxes = data.get("predictions", [])
    elif isinstance(data, list):
        boxes = data
    else:
        return

    # Separate special bars and normal bars
    special_bars = []
    normal_bars = []

    for item in boxes:
        # Normalize item structure
        if isinstance(item, list) and len(item) == 4:
            continue  # Skip raw boxes without type info if any

        btype = item.get("barline_type", item.get("type", "barline"))
        bbox = item.get("barline_location", item.get("bbox"))

        if not bbox:
            continue

        if btype in ["double_barline", "end_barline", "repeat", "final"]:
            special_bars.append({"bbox": bbox, "type": btype, "item": item})
        elif btype == "barline":
            normal_bars.append({"bbox": bbox, "type": btype, "item": item})

    if not special_bars:
        return

    print(f"\nScanning: {path}")

    match_counts = defaultdict(int)
    total_special = len(special_bars)

    for special in special_bars:
        s_box = special["bbox"]
        contained_bars = []

        for normal in normal_bars:
            n_box = normal["bbox"]
            iou, containment = calculate_iou(s_box, n_box)

            # If normal bar is mostly inside special bar
            if containment > 0.8:
                contained_bars.append(normal)

        match_counts[len(contained_bars)] += 1

        if len(contained_bars) == 0:
            print(f"  [MISSING INNER] {special['type']} at {s_box} contains 0 normal barlines.")
        # elif len(contained_bars) == 1:
        #     print(f"  [SINGLE INNER] {special['type']} at {s_box} contains 1 normal barline.")
        else:
            # Expected behavior for double/end bar is 2 contained bars
            pass

    print(f"  Summary for {total_special} special bars:")
    for count, freq in sorted(match_counts.items()):
        print(f"    Containing {count} normal bars: {freq}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--roots",
        nargs="+",
        default=[
            "data/training/annotations",
            "data/evaluation/annotations",
            "data/evaluation2/annotations",
        ],
    )
    args = parser.parse_args()

    files = []
    for root in args.roots:
        p = Path(root)
        if p.exists():
            # Only check "sorted" or "raw" files, preferring sorted
            # Actually, let's check all json files but filter for box files
            candidates = sorted(p.rglob("*.json"))
            for cand in candidates:
                if "boxes" in cand.name or "annotations" in cand.name:
                    files.append(cand)

    for f in files:
        audit_file(f)


if __name__ == "__main__":
    main()
