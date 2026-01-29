import json
import random
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


def category_matches(name, prefixes, names):
    if name in names:
        return True
    return any(name.startswith(prefix) for prefix in prefixes)


def visualize_deepscores_dataset(ds_root, sample_count=3, seed=42):
    output_dir = Path("logs/cnn_classifier/deepscores_vis_full")
    output_dir.mkdir(parents=True, exist_ok=True)

    seg_root = Path(ds_root) / "segmentation"
    img_root = Path(ds_root) / "images"

    # Load Annotation Data for FP
    json_path = Path(ds_root) / "deepscores_train.json"
    if not json_path.exists():
        json_path = Path(ds_root) / "deepscores_test.json"

    print(f"Loading annotations from {json_path}...")
    with json_path.open("r") as f:
        data = json.load(f)

    categories = data["categories"]
    cat_id_to_name = {str(k): v["name"] for k, v in categories.items()}
    images_info = {str(img["filename"]): img for img in data["images"]}
    annotations = data["annotations"]

    # FP definitions
    fp_prefixes = ["stem", "clef", "key", "accidental", "rest", "notehead", "beam"]
    fp_names = ["ledgerLine", "legerLine"]

    # TP definitions
    palette_index = 3
    min_area = 30
    min_height = 30
    vertical_ratio = 3.0

    seg_files = sorted(seg_root.glob("*_seg.png"))
    rng = random.Random(seed)
    rng.shuffle(seg_files)

    processed = 0
    for seg_path in seg_files:
        if processed >= sample_count:
            break

        img_name = seg_path.name.replace("_seg.png", ".png")
        img_info = images_info.get(img_name)
        if not img_info:
            continue

        img_path = img_root / img_name
        if not img_path.exists():
            continue

        print(f"Processing {img_name}...")
        img = cv2.imread(str(img_path))
        vis_img = img.copy()

        # 1. Draw TP Candidates (Green = Pass, Cyan/Red/Magenta = Fail)
        seg_np = load_palette_index(seg_path)
        mask = (seg_np == palette_index).astype(np.uint8) * 255
        comps = find_components(mask)

        tp_boxes = []
        for comp in comps:
            x1, y1, x2, y2 = comp["bbox"]
            color = (0, 255, 0)  # Green (Pass)
            is_tp = True

            if comp["area"] < min_area:
                color = (255, 255, 0)  # Cyan
                is_tp = False
            elif comp["h"] < min_height:
                color = (0, 0, 255)  # Red
                is_tp = False
            elif (comp["h"] / max(1, comp["w"])) < vertical_ratio:
                color = (255, 0, 255)  # Magenta
                is_tp = False

            # Draw TP candidate (Thick)
            cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 2)
            if is_tp:
                tp_boxes.append(comp["bbox"])

        # 2. Draw FP Candidates (Orange)
        ann_ids = img_info.get("ann_ids", [])
        for ann_id in ann_ids:
            ann = annotations.get(str(ann_id))
            if not ann:
                continue

            cat_ids = ann.get("cat_id", [])
            for cat_id in cat_ids:
                name = cat_id_to_name.get(str(cat_id))
                if name and category_matches(name, fp_prefixes, fp_names):
                    x1, y1, x2, y2 = [int(c) for c in ann["a_bbox"]]
                    # Draw FP (Orange)
                    cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 165, 255), 2)
                    break

        save_path = output_dir / f"vis_full_{img_name}"
        cv2.imwrite(str(save_path), vis_img)
        print(f"Saved: {save_path}")
        processed += 1


if __name__ == "__main__":
    visualize_deepscores_dataset(
        ds_root="/mnt/d/datasets/DeepScoresV2/ds2_dense", sample_count=5, seed=123
    )
