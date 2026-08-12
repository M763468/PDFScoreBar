"""Numbering step helpers."""

from __future__ import annotations

from copy import deepcopy
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


def rebase_mmr_overrides_to_page_local(
    payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Copy a page-specific MMR payload into one-page Score coordinates.

    Phase B persists MMR overrides with batch-global page indices. Phase C
    reconstructs one page at a time, so MMR overrides selected for that page
    must target the only page in the temporary Score (page index 0). The
    persisted Phase B payload remains unchanged.
    """
    if payload is None:
        return None

    rebased = deepcopy(payload)
    overrides = rebased.get("measure_overrides")
    if not isinstance(overrides, list):
        return rebased

    for override in overrides:
        if isinstance(override, dict) and "page" in override:
            override["page"] = 0
    return rebased


def _is_default_mmr_ocr_engine(ocr_engine: Optional[Any]) -> bool:
    if ocr_engine is None:
        return False
    from src.measure_numbering.mmr import MMROCREngine

    return type(ocr_engine) is MMROCREngine


def _should_replace_mmr_ocr_engine(
    ocr_engine: Optional[Any], rapidocr_provider: str = "auto"
) -> bool:
    if ocr_engine is None:
        return True
    if not _is_default_mmr_ocr_engine(ocr_engine):
        return False
    from src.measure_numbering.rapidocr_provider import normalize_rapidocr_provider

    provider_mode = normalize_rapidocr_provider(rapidocr_provider)
    return getattr(ocr_engine, "_rapidocr_provider_mode", None) != provider_mode


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
    rapidocr_provider: str = "auto",
) -> list[dict]:
    """Runs MMR detection in-process for a batch of pages."""
    from src.measure_numbering.mmr import MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        create_mmr_rapidocr,
        normalize_rapidocr_provider,
    )
    from src.pipeline.utils.io import write_json

    provider_mode = normalize_rapidocr_provider(rapidocr_provider)
    if _should_replace_mmr_ocr_engine(ocr_engine, provider_mode):
        provider_ocr_engine = create_mmr_rapidocr(provider_mode)
        if _is_default_mmr_ocr_engine(ocr_engine):
            ocr_engine.ocr_engine = provider_ocr_engine
            ocr_engine.enable_rotation_tta = enable_rotation_tta
        else:
            ocr_engine = MMROCREngine(
                enable_rotation_tta=enable_rotation_tta,
                ocr_engine=provider_ocr_engine,
            )
        setattr(ocr_engine, "_rapidocr_provider_mode", provider_mode)

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
