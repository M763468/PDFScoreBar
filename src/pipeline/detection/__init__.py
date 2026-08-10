"""Detection package providing barline detection orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.config import get_nested

from .utils import resolve_barlines_and_masks_config, resolve_paths_from_detection

__all__ = [
    "DetectorOrchestrator",
    "run_detection_step",
    "resolve_barlines_and_masks_config",
    "resolve_paths_from_detection",
]


def _install_standard_detector_hooks() -> None:
    from .connector_artifacts import (
        install_homr_connector_artifact_capture,
        install_homr_skip_existing_guard,
    )

    install_homr_connector_artifact_capture()
    install_homr_skip_existing_guard()


def run_detection_step(
    config: Dict[str, Any],
    images: List[Path],
    page_ids: List[str],
    run_id: str,
    run_dir: Path,
    *,
    dry_run: bool,
    in_memory_images: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Dispatch standard or verified Stage E production detection."""
    det_cfg = get_nested(config, "detection", default={}) or {}
    verified_route = str(
        det_cfg.get("detector_route", "standard")
    ) == "dense_full_pipeline" and bool(det_cfg.get("homr_profile"))
    if verified_route:
        # The verified route supervises its memory-heavy current x4 source phase
        # explicitly; do not import the standard heavy detector in this process.
        from .restored_orchestrator import run_detection_step as run_verified

        return run_verified(
            config,
            images,
            page_ids,
            run_id,
            run_dir,
            dry_run=dry_run,
            in_memory_images=in_memory_images,
        )

    _install_standard_detector_hooks()
    from .orchestrator import run_detection_step as run_standard

    return run_standard(
        config,
        images,
        page_ids,
        run_id,
        run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )


def __getattr__(name: str):
    if name == "DetectorOrchestrator":
        _install_standard_detector_hooks()
        from .orchestrator import DetectorOrchestrator

        return DetectorOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
