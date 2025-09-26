#!/usr/bin/env python3
"""Generate an overlay image to visualize homr barline predictions.

Usage:
    python tools/generate_barline_overlay.py --base <path/to/page.png> \
        --mask <path/to/debug_mask.png> --output <path/to/output.png>

The mask image is thresholded and colored red before being blended with the base
image so that detected barlines can be inspected visually.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="Path to the original score image")
    parser.add_argument("--mask", required=True, type=Path, help="Path to homr barline debug image")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the blended overlay image",
    )
    parser.add_argument(
        "--color",
        default="0,0,255",
        help="Comma separated B,G,R color for overlay (default: red)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.5,
        help="Overlay alpha in [0,1]; higher values emphasize the mask",
    )
    return parser


def parse_color(color_str: str) -> tuple[int, int, int]:
    try:
        parts = [int(v) for v in color_str.split(",")]
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Invalid color specification: {color_str}") from exc
    if len(parts) != 3:
        raise SystemExit("Color must contain exactly three comma separated integers")
    if not all(0 <= v <= 255 for v in parts):
        raise SystemExit("Color components must be within [0, 255]")
    return tuple(parts)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")

    mask_raw = cv2.imread(str(args.mask), cv2.IMREAD_GRAYSCALE)
    if mask_raw is None:
        raise SystemExit(f"Failed to load mask image: {args.mask}")

    if base.shape[:2] != mask_raw.shape[:2]:
        mask_raw = cv2.resize(mask_raw, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST)

    _, mask_binary = cv2.threshold(mask_raw, 0, 255, cv2.THRESH_BINARY)
    mask_bool = mask_binary > 0

    overlay = base.copy()
    overlay[mask_bool] = parse_color(args.color)

    alpha = min(max(args.alpha, 0.0), 1.0)
    blended = cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0.0)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), blended):
        raise SystemExit(f"Failed to write overlay image: {args.output}")


if __name__ == "__main__":
    main()
