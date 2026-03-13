"""Numbering step helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import torch

from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.utils.images import load_image_size


def empty_numbering_payload(page_number: int, image_path: Path) -> Dict[str, Any]:
    width, height = load_image_size(image_path)
    return {
        "pages": [
            {
                "page_number": page_number,
                "width": width,
                "height": height,
                "systems": [],
            }
        ]
    }


def build_add_measure_numbers_cmd(
    *,
    barlines: Path,
    staff_mask: Path,
    image: Path,
    output_json: Path,
    page_number: int,
    start_number: int,
    config_path: Optional[Path] = None,
    overlay_path: Optional[Path] = None,
    force_single_system: bool = False,
) -> list[str]:
    python_cmd = get_pipeline_python("numbering")
    cmd = python_cmd + [
        "tools/add_measure_numbers.py",
        "--barlines",
        str(barlines),
        "--staff-mask",
        str(staff_mask),
        "--image",
        str(image),
        "--output-json",
        str(output_json),
        "--page-number",
        str(page_number),
        "--start-number",
        str(start_number),
    ]
    if config_path:
        cmd += ["--config", str(config_path)]
    if overlay_path:
        cmd += ["--output-overlay", str(overlay_path)]
    if force_single_system:
        cmd.append("--force-single-system")
    return cmd


def run_mmr_batch(
    pages_data: list[dict],
    image_paths: list[Path],
    output_paths: list[Path],
    model_path: Path,
    device: torch.device,
    enable_rotation_tta: bool = False,
    threshold: float = 0.5,
    rescue_threshold: float = 0.1,
    debug_root: Optional[Path] = None,
    classifier: Optional[Any] = None,
    ocr_engine: Optional[Any] = None,
) -> list[dict]:
    """Runs MMR detection in-process for a batch of pages."""
    from src.measure_numbering.mmr import MMRProcessor
    from src.pipeline.utils.io import write_json

    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        enable_rotation_tta=enable_rotation_tta,
        threshold=threshold,
        rescue_threshold=rescue_threshold,
        classifier=classifier,
        ocr_engine=ocr_engine,
    )

    results = processor.process_pages(pages_data, image_paths, debug_root=debug_root)

    for result, output_path in zip(results, output_paths):
        write_json(output_path, result)

    return results
