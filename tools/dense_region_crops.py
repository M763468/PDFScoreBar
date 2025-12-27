#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


def find_top_windows(
    mask: np.ndarray,
    window_w: int,
    window_h: int,
    top_k: int,
) -> List[Tuple[int, int, int, int]]:
    h, w = mask.shape[:2]
    stride_x = max(10, window_w // 5)
    stride_y = max(10, window_h // 5)
    scores = []
    for y in range(0, max(1, h - window_h + 1), stride_y):
        for x in range(0, max(1, w - window_w + 1), stride_x):
            region = mask[y : y + window_h, x : x + window_w]
            score = int(region.sum())
            scores.append((score, x, y))
    scores.sort(reverse=True)
    windows = []
    for score, x, y in scores:
        if len(windows) >= top_k:
            break
        windows.append((x, y, x + window_w, y + window_h))
    return windows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--notehead-mask", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--top-k", type=int, default=2)
    ap.add_argument("--window-w-ratio", type=float, default=0.3)
    ap.add_argument("--window-h-ratio", type=float, default=0.2)
    args = ap.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        raise SystemExit(f"Failed to load {args.image}")
    base_h, base_w = img.shape[:2]

    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise SystemExit(f"Failed to load {args.notehead_mask}")
    if mask.shape[:2] != (base_h, base_w):
        mask = cv2.resize(mask, (base_w, base_h), interpolation=cv2.INTER_NEAREST)
    mask_bin = (mask > 0).astype(np.uint8)

    window_w = max(50, int(base_w * args.window_w_ratio))
    window_h = max(50, int(base_h * args.window_h_ratio))
    windows = find_top_windows(mask_bin, window_w, window_h, args.top_k)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    crops = []
    for idx, (x1, y1, x2, y2) in enumerate(windows):
        crop = img[y1:y2, x1:x2]
        crop_path = args.output_dir / f"crop_{idx}.png"
        cv2.imwrite(str(crop_path), crop)
        crops.append({"index": idx, "bbox": [x1, y1, x2, y2], "path": str(crop_path)})

    meta_path = args.output_dir / "crops.json"
    meta_path.write_text(json.dumps(crops, indent=2))


if __name__ == "__main__":
    main()
