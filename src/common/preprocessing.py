"""Image preprocessing helpers shared across evaluation scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import cv2
import numpy as np


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    """Return a grayscale view of the image without modifying the original."""

    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] in (3, 4):
        conversion = cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
        return cv2.cvtColor(image, conversion)
    raise ValueError("Unsupported image shape for grayscale conversion: %s" % (image.shape,))


def vertical_closing_blend(
    image: np.ndarray,
    *,
    kernel_height: int = 7,
    closing_blend: float = 0.4,
) -> np.ndarray:
    """Enhance vertical barlines by blending a morphological closing.

    Args:
        image: Input image in BGR, BGRA, or single-channel grayscale format.
        kernel_height: Height of the vertical structuring element used for closing.
        closing_blend: Weight of the closed image in the final blend (0..1).

    Returns:
        Processed image with the same channel configuration as the input.

    Raises:
        ValueError: If the kernel height or blend factor is outside the allowed range.
    """

    if kernel_height < 1:
        raise ValueError("kernel_height must be >= 1")
    if closing_blend < 0 or closing_blend > 1:
        raise ValueError("closing_blend must be within [0, 1]")

    gray = _to_grayscale(image)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(kernel_height)))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    original_weight = 1.0 - closing_blend
    blended = cv2.addWeighted(gray, original_weight, closed, closing_blend, 0.0)

    if image.ndim == 2:
        return blended
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(blended, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        bgr = cv2.cvtColor(blended, cv2.COLOR_GRAY2BGR)
        alpha = image[:, :, 3]
        return np.dstack((bgr, alpha))
    raise ValueError("Unsupported image shape: %s" % (image.shape,))


def vertical_closing_blend_file(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    kernel_height: int = 7,
    closing_blend: float = 0.4,
    ensure_parent: bool = True,
) -> Path:
    """Apply :func:`vertical_closing_blend` and persist the result."""

    src_path = Path(input_path)
    dst_path = Path(output_path)
    image = cv2.imread(str(src_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Unable to load image: {src_path}")
    processed = vertical_closing_blend(
        image,
        kernel_height=kernel_height,
        closing_blend=closing_blend,
    )
    if ensure_parent:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(dst_path), processed):
        raise IOError(f"Failed to write processed image: {dst_path}")
    return dst_path

