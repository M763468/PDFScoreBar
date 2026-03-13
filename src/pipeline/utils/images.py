"""Image collection and page id helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2  # type: ignore

from src.pipeline.core.config import get_nested


def collect_images(config: Dict[str, Any], run_dir: Path) -> List[Path]:
    pdf_opts = get_nested(config, "inputs", "pdf_to_images", default={}) or {}
    output_dir = run_dir / "inputs" / "images"
    image_glob = pdf_opts.get("image_glob", "page_*.png")

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
        # TODO: Support explicit image list inputs for dry-run validation.
        raise FileNotFoundError(f"No images found in {output_dir} matching {image_glob}")
    return images


def resolve_page_ids(config: Dict[str, Any], images: List[Path]) -> List[str]:
    prefix = get_nested(config, "inputs", "pdf_to_images", "prefix", default="page")
    return [f"{prefix}_{index:03d}" for index in range(1, len(images) + 1)]


def load_image_size(image_path: Path) -> Tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        return 0, 0
    height, width = image.shape[:2]
    return width, height
