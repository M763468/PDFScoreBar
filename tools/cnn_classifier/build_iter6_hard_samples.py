import shutil
from pathlib import Path

import cv2


def extract_crop(img, bbox, pad_scale=3.0, target_size=(128, 256)):
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    h = y2 - y1
    ch = int(h * pad_scale)
    ch = max(48, min(256, ch))
    cw = ch // 2

    y1_c, y2_c = max(0, cy - ch // 2), min(img.shape[0], cy + ch // 2)
    x1_c, x2_c = max(0, cx - cw // 2), min(img.shape[1], cx + cw // 2)
    crop = img[y1_c:y2_c, x1_c:x2_c]

    if crop.shape[0] < ch or crop.shape[1] < cw:
        pad_y1 = ch // 2 - (cy - y1_c)
        pad_y2 = ch // 2 - (y2_c - cy)
        pad_x1 = cw // 2 - (cx - x1_c)
        pad_x2 = cw // 2 - (x2_c - cx)
        crop = cv2.copyMakeBorder(
            crop, pad_y1, pad_y2, pad_x1, pad_x2, cv2.BORDER_CONSTANT, value=[255, 255, 255]
        )

    return cv2.resize(crop, target_size)


def main():
    failures = [
        ("Sibelius-Violin_Concerto-Viola", "page_004", [2713, 3166, 2720, 3274], "tp"),
        ("Shostakovich-Sym5-Va", "page_003", [948, 789, 952, 889], "fp"),
        ("Va_Prokofiev_Symphony1", "page_005", [1496, 3484, 1500, 3587], "fp"),
    ]

    output_root = Path("datasets/cnn_classifier_v6_hard_mining")
    if output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "train/tp").mkdir(parents=True)
    (output_root / "train/fp").mkdir(parents=True)
    (output_root / "val/tp").mkdir(parents=True)
    (output_root / "val/fp").mkdir(parents=True)

    for score, page, bbox, label in failures:
        img_path = Path(f"data/evaluation2/images/{score}/{page}.png")
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Failed to load {img_path}")
            continue

        crop = extract_crop(img, bbox)

        # 100x Oversample for Train
        for i in range(100):
            out_name = f"{score}_{page}_{i:03d}.png"
            cv2.imwrite(str(output_root / "train" / label / out_name), crop)

        # 1x for Val (to monitor progress)
        cv2.imwrite(str(output_root / "val" / label / f"{score}_{page}.png"), crop)

    print(f"Iter 6 hard samples built at {output_root}")


if __name__ == "__main__":
    main()
