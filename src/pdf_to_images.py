#!/usr/bin/env python3
"""Utility to render PDF pages into images with configurable DPI and resampling."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np

DEFAULT_PDF = Path("data/training/pdfs/IMSLP19910-PMLP01607-Beethoven_Symphony_9_V1.pdf")
DEFAULT_OUTPUT = Path("data/training/images")
INTERPOLATION_MAP = {
    "nearest": cv2.INTER_NEAREST,
    "linear": cv2.INTER_LINEAR,
    "area": cv2.INTER_AREA,
    "cubic": cv2.INTER_CUBIC,
    "lanczos": cv2.INTER_LANCZOS4,
}


class PdfConversionError(RuntimeError):
    """Raised when a page cannot be rendered or saved."""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help="Path to the PDF file to convert",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory where rendered images will be written",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=300.0,
        help="Rendering DPI passed to PyMuPDF",
    )
    parser.add_argument(
        "--pages",
        type=str,
        help="Comma-separated list of 1-based page indices to render (default: all)",
    )
    parser.add_argument(
        "--target-width",
        type=int,
        help="Optional target width in pixels for the output images",
    )
    parser.add_argument(
        "--target-height",
        type=int,
        help="Optional target height in pixels for the output images",
    )
    parser.add_argument(
        "--interpolation",
        choices=sorted(INTERPOLATION_MAP.keys()),
        default="area",
        help="Interpolation mode used when resizing",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="page",
        help="Filename prefix for generated images",
    )
    parser.add_argument(
        "--format",
        choices=["png", "jpg", "jpeg", "tiff", "bmp"],
        default="png",
        help="Image file format / extension",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing files",
    )
    parser.add_argument(
        "--alpha",
        action="store_true",
        help="Preserve alpha channel when rendering (default: drop alpha)",
    )
    return parser.parse_args(argv)


def normalise_pages(pages_arg: Optional[str], total_pages: int) -> List[int]:
    if not pages_arg:
        return list(range(total_pages))
    indices: List[int] = []
    for token in pages_arg.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            page_index = int(token)
        except ValueError as exc:
            raise ValueError(f"Invalid page index: {token}") from exc
        if page_index < 1 or page_index > total_pages:
            raise ValueError(f"Page index out of bounds: {page_index}")
        indices.append(page_index - 1)
    return sorted(set(indices))


def pixmap_to_array(pix: fitz.Pixmap, *, keep_alpha: bool) -> np.ndarray:
    if pix.alpha and not keep_alpha:
        pix = fitz.Pixmap(pix, 0)  # Drop alpha channel
    buffer = pix.samples
    channels = pix.n
    array = np.frombuffer(buffer, dtype=np.uint8)
    if channels == 1:
        array = array.reshape(pix.height, pix.width)
        return array
    array = array.reshape(pix.height, pix.width, channels)
    if channels == 3:
        return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    if channels == 4:
        return cv2.cvtColor(array, cv2.COLOR_RGBA2BGRA)
    raise PdfConversionError(f"Unsupported channel count: {channels}")


def resize_image(
    image: np.ndarray,
    *,
    target_width: Optional[int],
    target_height: Optional[int],
    interpolation: str,
) -> np.ndarray:
    if target_width is None and target_height is None:
        return image
    height, width = image.shape[:2]
    if target_width is None:
        scale = target_height / height
        target_width = max(1, int(round(width * scale)))
    if target_height is None:
        scale = target_width / width
        target_height = max(1, int(round(height * scale)))
    interp_flag = INTERPOLATION_MAP[interpolation]
    return cv2.resize(image, (target_width, target_height), interpolation=interp_flag)


def save_image(path: Path, image: np.ndarray, *, fmt: str) -> None:
    success = cv2.imwrite(str(path), image)
    if not success:
        raise PdfConversionError(f"Failed to write image: {path}")


def render_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: float,
    pages: Sequence[int],
    prefix: str,
    fmt: str,
    keep_alpha: bool,
    target_width: Optional[int],
    target_height: Optional[int],
    interpolation: str,
    overwrite: bool,
) -> List[Path]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    with fitz.open(pdf_path) as document:
        for page_index in pages:
            page = document.load_page(page_index)
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pix = page.get_pixmap(matrix=matrix, alpha=keep_alpha)
            image = pixmap_to_array(pix, keep_alpha=keep_alpha)
            image = resize_image(
                image,
                target_width=target_width,
                target_height=target_height,
                interpolation=interpolation,
            )
            name = f"{prefix}_{page_index + 1:03d}.{fmt}"
            destination = output_dir / name
            if destination.exists() and not overwrite:
                raise PdfConversionError(f"Refusing to overwrite existing file: {destination}")
            save_image(destination, image, fmt=fmt)
            written.append(destination)
    return written


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    pages: List[int]
    with fitz.open(args.pdf) as doc:
        pages = normalise_pages(args.pages, doc.page_count)
    written = render_pdf(
        args.pdf,
        args.output_dir,
        dpi=args.dpi,
        pages=pages,
        prefix=args.prefix,
        fmt=args.format,
        keep_alpha=args.alpha,
        target_width=args.target_width,
        target_height=args.target_height,
        interpolation=args.interpolation,
        overwrite=args.overwrite,
    )
    for path in written:
        print(f"Saved {path}")


if __name__ == "__main__":
    main()

