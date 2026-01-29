from pathlib import Path

import cv2


def extract_crop(img, bbox, target_size=(256, 256)):
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    h, w = img.shape[:2]

    half_h, half_w = target_size[0] // 2, target_size[1] // 2

    y_start = max(0, cy - half_h)
    y_end = min(h, cy + half_h)
    x_start = max(0, cx - half_w)
    x_end = min(w, cx + half_w)

    crop = img[y_start:y_end, x_start:x_end]
    # Pad if necessary
    pad_y_top = half_h - (cy - y_start)
    pad_y_bottom = half_h - (y_end - cy)
    pad_x_left = half_w - (cx - x_start)
    pad_x_right = half_w - (x_end - cx)

    if pad_y_top > 0 or pad_y_bottom > 0 or pad_x_left > 0 or pad_x_right > 0:
        crop = cv2.copyMakeBorder(
            crop,
            pad_y_top,
            pad_y_bottom,
            pad_x_left,
            pad_x_right,
            cv2.BORDER_CONSTANT,
            value=[255, 255, 255],
        )

    return crop


def main():
    image_root = Path("data/evaluation2/images")
    output_dir = Path("datasets/cnn_classifier_v3_active_learning/splits/train/fp")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Coordinates from previous analysis (approximate center from FP labels)
    # Shosrakovich-Sym5-Va_page_016_FP_2713_3681.png -> (2713, 3681)
    # Shosrakovich-Sym5-Va_page_019_FP_1308_420.png -> (1308, 420)

    targets = [
        ("Shosrakovich-Sym5-Va/page_016", (2713, 3681)),
        ("Shosrakovich-Sym5-Va/page_019", (1308, 420)),
    ]

    for page_rel, (tx, ty) in targets:
        img_path = image_root / f"{page_rel}.png"
        if not img_path.exists():
            print(f"Not found: {img_path}")
            continue

        print(f"Extracting from {page_rel} at ({tx}, {ty})")
        img = cv2.imread(str(img_path))

        # Width/height for the "barline" box
        # Typical barline width 4-8, height ~240
        # The FP crops showed these were fairly long
        bw, bh = 6, 240
        bbox = [tx - bw // 2, ty - bh // 2, tx + bw // 2, ty + bh // 2]

        crop = extract_crop(img, bbox)

        # Save with a high prefix to make it easy to find/weight if needed
        fname = f"hard_neg_20260112_{page_rel.replace('/', '_')}_{tx}_{ty}.png"
        cv2.imwrite(str(output_dir / fname), crop)
        print(f"Saved to {output_dir / fname}")


if __name__ == "__main__":
    main()
