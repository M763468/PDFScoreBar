"""Numbering step helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from src.pipeline.images import load_image_size


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
    cmd = [
        sys.executable,
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


def build_generate_overrides_cmd(
    *,
    numbering_json: Path,
    image: Path,
    output_overrides: Path,
    model_path: Optional[Path],
    enable_rotation_tta: bool,
    debug_image: Optional[Path] = None,
) -> list[str]:
    cmd = [
        sys.executable,
        "tools/generate_numbering_overrides.py",
        "--numbering-json",
        str(numbering_json),
        "--image",
        str(image),
        "--output-overrides",
        str(output_overrides),
    ]
    if model_path:
        cmd += ["--model-path", str(model_path)]
    if debug_image:
        cmd += ["--debug-image", str(debug_image)]
    if enable_rotation_tta:
        cmd.append("--enable-rotation-tta")
    return cmd
