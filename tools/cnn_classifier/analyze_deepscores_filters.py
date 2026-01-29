from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_palette_index(seg_path: Path) -> np.ndarray:
    seg_img = Image.open(seg_path)
    if seg_img.mode != "P":
        seg_img = seg_img.convert("P")
    return np.array(seg_img)


def find_components(mask: np.ndarray):
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx].tolist()
        comps.append(
            {
                "label": idx,
                "bbox": [x, y, x + w - 1, y + h - 1],
                "w": w,
                "h": h,
                "area": area,
            }
        )
    return comps


def analyze_deepscores_components(
    ds_root, palette_index, min_area, min_height, vertical_ratio, sample_count
):
    print(f"Analyzing DeepScores segmentation (Palette {palette_index})...")
    seg_root = Path(ds_root) / "segmentation"
    seg_files = sorted(seg_root.glob("*_seg.png"))

    if not seg_files:
        print("No segmentation files found.")
        return

    total_comps = 0
    passed_comps = 0
    filtered_by_area = 0
    filtered_by_height = 0
    filtered_by_ratio = 0

    analyzed_count = 0

    for seg_path in seg_files:
        if analyzed_count >= sample_count:
            break

        try:
            seg_np = load_palette_index(seg_path)
        except Exception as e:
            print(f"Error loading {seg_path}: {e}")
            continue

        mask = (seg_np == palette_index).astype(np.uint8) * 255
        comps = find_components(mask)

        if not comps:
            continue

        analyzed_count += 1

        for comp in comps:
            total_comps += 1

            is_valid = True
            if comp["area"] < min_area:
                filtered_by_area += 1
                is_valid = False
            elif comp["h"] < min_height:  # Check order matches build_cnn_dataset.py
                filtered_by_height += 1
                is_valid = False
            elif (comp["h"] / max(1, comp["w"])) < vertical_ratio:
                filtered_by_ratio += 1
                is_valid = False

            if is_valid:
                passed_comps += 1

    print("-" * 30)
    print(f"Analyzed {analyzed_count} images containing palette {palette_index}.")
    print(f"Total components found: {total_comps}")
    print(
        f"Passed filters (TP candidates): {passed_comps} ({passed_comps / total_comps * 100:.1f}%)"
    )
    print("-" * 30)
    print("Filtered out:")
    print(f"  Area < {min_area}: {filtered_by_area} ({filtered_by_area / total_comps * 100:.1f}%)")
    print(
        f"  Height < {min_height}: {filtered_by_height} ({filtered_by_height / total_comps * 100:.1f}%)"
    )
    print(
        f"  H/W Ratio < {vertical_ratio}: {filtered_by_ratio} ({filtered_by_ratio / total_comps * 100:.1f}%)"
    )
    print("-" * 30)


if __name__ == "__main__":
    analyze_deepscores_components(
        ds_root="/mnt/d/datasets/DeepScoresV2/ds2_dense",
        palette_index=3,
        min_area=30,
        min_height=30,
        vertical_ratio=3.0,
        sample_count=50,
    )
