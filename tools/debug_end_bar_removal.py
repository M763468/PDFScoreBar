import argparse
import json
import sys

import cv2

# Fix import path
sys.path.append("src")

from measure_numbering.types import Barline, BBox


def load_barlines(path):
    with open(path, "r") as f:
        data = json.load(f)
    return [Barline(bbox=BBox(*item["barline_location"])) for item in data]


def debug_end_bar_removal(image_path, barline_path, output_path):
    print(f"Debugging {image_path}")

    # Load Image
    img = cv2.imread(str(image_path))
    if img is None:
        print("Failed to load image")
        return

    # Load Barlines
    barlines = load_barlines(barline_path)

    # Group barlines into systems (simple Y clustering)
    systems = []
    # copy barlines to a working list
    pool = sorted(barlines, key=lambda b: (b.bbox.y1 + b.bbox.y2) / 2)

    while pool:
        seed = pool.pop(0)
        current_system = [seed]

        # Find all barlines that overlap vertically with seed
        # Heuristic: overlap > 50% of the shorter one
        seed_h = seed.bbox.y2 - seed.bbox.y1

        next_pool = []
        for other in pool:
            # Check overlap
            y_min = max(seed.bbox.y1, other.bbox.y1)
            y_max = min(seed.bbox.y2, other.bbox.y2)
            overlap = max(0, y_max - y_min)

            # Simple check: if overlap is substantial
            other_h = other.bbox.y2 - other.bbox.y1
            if overlap > 0.5 * min(seed_h, other_h):
                current_system.append(other)
            else:
                next_pool.append(other)

        pool = next_pool
        systems.append(current_system)

    print(f"Found {len(systems)} pseudo-systems.")

    count_removed = 0

    for sys_bars in systems:
        # Sort by X
        sys_bars.sort(key=lambda b: b.bbox.x1)

        for i in range(len(sys_bars) - 1):
            b1 = sys_bars[i]
            b2 = sys_bars[i + 1]

            # Measure (Gap) definition
            mx1 = b1.bbox.x2
            mx2 = b2.bbox.x1
            width = mx2 - mx1

            # Use shared Y range for visualization
            my1 = min(b1.bbox.y1, b2.bbox.y1)
            my2 = max(b1.bbox.y2, b2.bbox.y2)

            if width < 25:  # MIN_MEASURE_WIDTH
                count_removed += 1
                print(f"Removed Gap: Width={width:.1f}, X={mx1:.1f}, Y={my1:.1f}")
                # Draw Red Filled
                cv2.rectangle(img, (int(mx1), int(my1)), (int(mx2), int(my2)), (0, 0, 255), -1)
            else:
                # Valid measure - Green Outline
                cv2.rectangle(img, (int(mx1), int(my1)), (int(mx2), int(my2)), (0, 255, 0), 2)

    print(f"Total Removed Gaps: {count_removed}")

    cv2.imwrite(str(output_path), img)
    print(f"Saved debug overlay to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--barlines", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sys.path.append("src")  # Ensure src is in path
    debug_end_bar_removal(args.image, args.barlines, args.output)
