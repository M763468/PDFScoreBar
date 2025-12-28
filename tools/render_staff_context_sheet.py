#!/usr/bin/env python3
import argparse
from pathlib import Path

import cv2
import numpy as np


def put_text_block(img, lines, origin=(10, 20), color=(0, 0, 0)):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)
        y += 18


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--crop-overlay", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--legend", required=True)
    args = ap.parse_args()

    page = cv2.imread(args.page, cv2.IMREAD_COLOR)
    crop = cv2.imread(args.crop_overlay, cv2.IMREAD_COLOR)
    if page is None:
        raise SystemExit(f"Failed to load page image: {args.page}")
    if crop is None:
        raise SystemExit(f"Failed to load crop overlay: {args.crop_overlay}")

    # Resize crop to fit page height
    page_h, page_w = page.shape[:2]
    crop_h, crop_w = crop.shape[:2]
    scale = page_h / crop_h
    new_w = int(crop_w * scale)
    crop_resized = cv2.resize(crop, (new_w, page_h), interpolation=cv2.INTER_AREA)

    padding = 20
    canvas_w = page_w + padding + crop_resized.shape[1]
    canvas = np.full((page_h, canvas_w, 3), 255, dtype=np.uint8)
    canvas[:, :page_w] = page
    canvas[:, page_w + padding :] = crop_resized

    lines = [
        args.legend,
        f"page: {args.page}",
        f"crop: {args.crop_overlay}",
    ]
    put_text_block(canvas, lines, origin=(10, 20), color=(0, 0, 0))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), canvas):
        raise SystemExit(f"Failed to write output: {out}")


if __name__ == "__main__":
    main()
