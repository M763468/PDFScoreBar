"""Image collection and page id helpers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2  # type: ignore
import numpy as np

from src.pipeline.core.config import get_nested

logger = logging.getLogger(__name__)

# Global in-memory image cache: stem -> np.ndarray
_IMAGE_CACHE: Dict[str, np.ndarray] = {}


def get_image_cache() -> Dict[str, np.ndarray]:
    return _IMAGE_CACHE


def clear_image_cache() -> None:
    _IMAGE_CACHE.clear()


def _review_package_enabled(config: Dict[str, Any]) -> bool:
    review_cfg = get_nested(config, "outputs", "review", default={}) or {}
    return isinstance(review_cfg, dict) and bool(review_cfg.get("manual_correction_package", False))


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _stage_external_review_images(images: List[Path], run_dir: Path) -> List[Path]:
    staged_dir = run_dir / "inputs" / "images"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_images: List[Path] = []

    for image in images:
        src = Path(image)
        if _path_is_inside(src, run_dir):
            staged_images.append(src)
            continue

        dest = staged_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        staged_images.append(dest)

    return staged_images


def collect_images(
    config: Dict[str, Any],
    run_dir: Path,
    in_memory_images: Dict[str, np.ndarray] | None = None,
) -> List[Path]:
    pdf_opts = get_nested(config, "inputs", "pdf_to_images", default={}) or {}
    output_dir = run_dir / "inputs" / "images"
    image_glob = pdf_opts.get("image_glob", "page_*.png")

    # If we have in-memory images, we can construct virtual paths
    if in_memory_images:
        images = []
        fmt = pdf_opts.get("format", "png")
        for stem in sorted(in_memory_images.keys()):
            images.append(output_dir / f"{stem}.{fmt}")
        return images

    if not output_dir.exists():
        external_dir = pdf_opts.get("output_dir")
        if external_dir:
            output_dir = Path(external_dir)
        else:
            raise ValueError("PDF images not found. Enable pdf_to_images or specify output_dir.")

    images = sorted(Path(output_dir).glob(image_glob))
    if not images:
        external_dir = pdf_opts.get("output_dir")
        if external_dir:
            external_dir = Path(external_dir)
            images = sorted(external_dir.glob(image_glob))
    if not images:
        raise FileNotFoundError(f"No images found in {output_dir} matching {image_glob}")

    if _review_package_enabled(config):
        images = _stage_external_review_images(images, run_dir)

    return images


def resolve_page_ids(config: Dict[str, Any], images: List[Path]) -> List[str]:
    # Try to extract page IDs from stems first to be more robust
    stems = [img.stem for img in images]
    # If stems look like page_001, page_002, we use them
    if all(s.startswith("page_") for s in stems):
        return stems

    prefix = get_nested(config, "inputs", "pdf_to_images", "prefix", default="page")
    return [f"{prefix}_{index:03d}" for index in range(1, len(images) + 1)]


def load_image(
    image_path: Path, in_memory_images: Dict[str, np.ndarray] | None = None
) -> np.ndarray:
    """Loads an image, checking the in-memory cache first.
    If the file exists on disk, we prefer it to avoid stem collisions (e.g. SR images).
    """
    if image_path.exists():
        image = cv2.imread(str(image_path))
        if image is not None:
            return image

    stem = image_path.stem
    if in_memory_images and stem in in_memory_images:
        return in_memory_images[stem]

    # Fallback to global cache
    if stem in _IMAGE_CACHE:
        return _IMAGE_CACHE[stem]

    # This part is technically redundant if we check exists() above,
    # but kept for error handling.
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Failed to load image: {image_path}")
    return image


def load_image_size(
    image_path: Path, in_memory_images: Dict[str, np.ndarray] | None = None
) -> Tuple[int, int]:
    try:
        image = load_image(image_path, in_memory_images)
        height, width = image.shape[:2]
        return width, height
    except FileNotFoundError:
        return 0, 0
