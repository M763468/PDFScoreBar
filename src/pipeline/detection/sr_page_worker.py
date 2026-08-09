"""Generate one verified-profile SR page in an isolated process."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from src.common.preprocessing import apply_advanced_sr
from src.pipeline.utils.images import load_image


def run(
    *,
    image: Path,
    output: Path,
    scale: int,
    tile: int,
    tile_pad: int,
    fp32: bool,
) -> None:
    if scale not in (2, 4):
        raise ValueError(f"Unsupported verified-profile SR scale: {scale}")
    model_name = "RealESRGAN_x4plus" if scale == 4 else "RealESRGAN_x2plus"
    image_bgr = load_image(image)
    upscaled, _upsampler = apply_advanced_sr(
        image_bgr,
        model_name=model_name,
        scale=scale,
        tile=tile,
        tile_pad=tile_pad,
        fp32=fp32,
        upsampler=None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), upscaled):
        raise RuntimeError(f"Failed to write SR image: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", type=int, required=True)
    parser.add_argument("--tile", type=int, default=-1)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--fp32", action="store_true")
    args = parser.parse_args()
    run(
        image=args.image,
        output=args.output,
        scale=args.scale,
        tile=args.tile,
        tile_pad=args.tile_pad,
        fp32=args.fp32,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
