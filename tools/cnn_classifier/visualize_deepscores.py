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


def visualize_deepscores_filters(ds_root, sample_count=1):
    output_dir = Path("logs/cnn_classifier/deepscores_vis")
    output_dir.mkdir(parents=True, exist_ok=True)

    seg_root = Path(ds_root) / "segmentation"
    img_root = Path(ds_root) / "images"
    seg_files = sorted(seg_root.glob("*_seg.png"))

    # Filter Parameters
    palette_index = 3
    min_area = 30
    min_height = 30
    vertical_ratio = 3.0

    count = 0
    for seg_path in seg_files:
        if count >= sample_count:
            break

        # Try finding one with enough components to be interesting
        seg_np = load_palette_index(seg_path)
        mask = (seg_np == palette_index).astype(np.uint8) * 255
        comps = find_components(mask)

        if len(comps) < 5:
            continue

        count += 1
        img_name = seg_path.name.replace("_seg.png", ".png")
        img_path = img_root / img_name
        if not img_path.exists():
            continue

        img = cv2.imread(str(img_path))
        vis_img = img.copy()

        for comp in comps:
            x1, y1, x2, y2 = comp["bbox"]
            color = (0, 255, 0)  # Green (Pass)

            if comp["area"] < min_area:
                color = (255, 255, 0)  # Cyan (Area fail)
            elif comp["h"] < min_height:
                color = (0, 0, 255)  # Red (Height fail)
            elif (comp["h"] / max(1, comp["w"])) < vertical_ratio:
                color = (255, 0, 255)  # Magenta (Ratio fail)

            # Thick line for visibility
            cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 3)

            # Draw text if it's large enough
            # if comp["h"] > 20:
            #    cv2.putText(vis_img, str(comp["h"]), (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        save_path = output_dir / f"vis_{img_name}"
        cv2.imwrite(str(save_path), vis_img)
        print(f"Saved visualization: {save_path}")


if __name__ == "__main__":
    visualize_deepscores_filters(ds_root="/mnt/d/datasets/DeepScoresV2/ds2_dense", sample_count=1)
