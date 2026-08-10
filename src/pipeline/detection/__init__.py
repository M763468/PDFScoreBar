"""Detection package providing barlines detection orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.config import get_nested

from .connector_artifacts import (
    install_homr_connector_artifact_capture,
    install_homr_skip_existing_guard,
)
from .utils import resolve_barlines_and_masks_config, resolve_paths_from_detection

install_homr_connector_artifact_capture()
install_homr_skip_existing_guard()

__all__ = [
    "DetectorOrchestrator",
    "run_detection_step",
    "resolve_barlines_and_masks_config",
    "resolve_paths_from_detection",
]


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
    """Dispatch detection without importing the heavy detector in the parent process."""
    execution_mode = str(
        get_nested(config, "detection", "execution_mode", default="in_process")
    )
    if execution_mode == "isolated_per_page":
        from .isolation import run_detection_isolated_per_page

        return run_detection_isolated_per_page(
            config,
            images,
            page_ids,
            run_id,
            run_dir,
            dry_run=dry_run,
            in_memory_images=in_memory_images,
        )

    from .restored_orchestrator import run_detection_step as run_in_process

    return run_in_process(
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
        from .restored_orchestrator import DetectorOrchestrator

        return DetectorOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
