#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_palette_index(seg_path: Path) -> np.ndarray:
    seg_img = Image.open(seg_path)
    if seg_img.mode != "P":
        seg_img = seg_img.convert("P")
    return np.array(seg_img)


def load_seg_rgb(seg_path: Path) -> np.ndarray:
    seg_img = Image.open(seg_path)
    return np.array(seg_img.convert("RGB"))


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


def draw_boxes(image: np.ndarray, boxes, color=(255, 0, 0)) -> np.ndarray:
    out = image.copy()
    for box in boxes:
        x1, y1, x2, y2 = box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
    return out


def save_crops(seg_rgb, comps, out_dir: Path, prefix: str, max_crops: int | None):
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for idx, comp in enumerate(comps):
        if max_crops is not None and saved >= max_crops:
            break
        x1, y1, x2, y2 = comp["bbox"]
        pad = 10
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(seg_rgb.shape[1] - 1, x2 + pad)
        cy2 = min(seg_rgb.shape[0] - 1, y2 + pad)
        crop = seg_rgb[cy1 : cy2 + 1, cx1 : cx2 + 1]
        crop = draw_boxes(crop, [[x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1]])
        out_path = out_dir / f"{prefix}_{idx:03d}.png"
        Image.fromarray(crop).save(out_path)
        saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser(
        description="Extract components for a palette index from DeepScores segmentation."
    )
    parser.add_argument(
        "--seg-root",
        type=Path,
        default=Path("/mnt/d/datasets/DeepScoresV2/ds2_dense/segmentation"),
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("logs/deepscores_tp/color_components")
    )
    parser.add_argument("--palette-index", type=int, default=165)
    parser.add_argument("--min-area", type=int, default=50)
    parser.add_argument("--min-height", type=int, default=30)
    parser.add_argument("--vertical-ratio", type=float, default=3.0)
    parser.add_argument("--max-images", type=int, default=5)
    parser.add_argument("--max-crops", type=int, default=50)
    parser.add_argument("--images", nargs="*", help="Specific segmentation filenames.")

    args = parser.parse_args()
    seg_root = args.seg_root
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    if args.images:
        seg_files = [seg_root / name for name in args.images]
    else:
        seg_files = sorted(seg_root.glob("*_seg.png"))[: args.max_images]

    summary = []
    for seg_path in seg_files:
        if not seg_path.exists():
            continue
        seg_np = load_palette_index(seg_path)
        seg_rgb = load_seg_rgb(seg_path)
        mask = (seg_np == args.palette_index).astype(np.uint8) * 255
        comps = find_components(mask)

        comps = [c for c in comps if c["area"] >= args.min_area]
        vertical = [
            c
            for c in comps
            if c["h"] >= args.min_height and (c["h"] / max(1, c["w"])) >= args.vertical_ratio
        ]
        non_vertical = [c for c in comps if c not in vertical]

        image_out = output_root / seg_path.stem
        image_out.mkdir(parents=True, exist_ok=True)

        overlay = draw_boxes(seg_rgb, [c["bbox"] for c in vertical], color=(0, 255, 0))
        overlay_path = image_out / "vertical_overlay.png"
        Image.fromarray(overlay).save(overlay_path)

        vert_crops = save_crops(
            seg_rgb, vertical, image_out / "vertical_crops", "vert", args.max_crops
        )
        other_crops = save_crops(
            seg_rgb, non_vertical, image_out / "other_crops", "other", args.max_crops
        )

        summary.append(
            {
                "image": str(seg_path),
                "palette_index": args.palette_index,
                "total_components": len(comps),
                "vertical_components": len(vertical),
                "non_vertical_components": len(non_vertical),
                "vertical_crops_saved": vert_crops,
                "other_crops_saved": other_crops,
                "output_dir": str(image_out),
            }
        )

    summary_path = output_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"Wrote summary: {summary_path}")


if __name__ == "__main__":
    main()
