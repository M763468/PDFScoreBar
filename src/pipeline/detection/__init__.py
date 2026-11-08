"""Detection package providing barline detection orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core import get_nested

from .config import DENSE_ROUTE_NAME, resolve_detector_route
from .model_selection import model_validation_mode
from .utils import resolve_barlines_and_masks_config, resolve_paths_from_detection

__all__ = [
    "DetectorOrchestrator",
    "run_detection_step",
    "resolve_barlines_and_masks_config",
    "resolve_paths_from_detection",
    "DENSE_ROUTE_NAME",
]


def _detector_route(config: Dict[str, Any]) -> str:
    det_cfg = get_nested(config, "detection", default={}) or {}
    route = resolve_detector_route(det_cfg)
    model_validation_mode(det_cfg)
    return route


def _validate_verified_image_stems(images: List[Path]) -> None:
    """Reject ambiguous verified-route calls before profile artifacts can collide."""
    by_stem: dict[str, list[Path]] = {}
    for image in images:
        by_stem.setdefault(image.stem, []).append(image)

    duplicates = {stem: paths for stem, paths in by_stem.items() if len(paths) > 1}
    if not duplicates:
        return

    details = ", ".join(
        f"{stem}=[{', '.join(str(path) for path in paths)}]"
        for stem, paths in sorted(duplicates.items())
    )
    raise ValueError(
        "Verified dense_full_pipeline detection requires unique image stems within one call; "
        f"duplicate stems would overwrite profile outputs: {details}. "
        "Split detection calls by score."
    )


class DetectorOrchestrator:
    """Construct the single verified dense detector orchestrator (#522)."""

    def __new__(
        cls,
        config: Dict[str, Any],
        images: List[Path],
        run_id: str,
        run_dir: Path,
        *,
        dry_run: bool,
        in_memory_images: Dict[str, Any] | None = None,
    ):
        _detector_route(config)
        _validate_verified_image_stems(images)
        from .dense_orchestrator_batch_sr import (
            DetectorOrchestrator as VerifiedDetectorOrchestrator,
        )

        return VerifiedDetectorOrchestrator(
            config=config,
            images=images,
            run_id=run_id,
            run_dir=run_dir,
            dry_run=dry_run,
            in_memory_images=in_memory_images,
        )


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
    """Run the single verified dense detector route (#522)."""
    _detector_route(config)
    _validate_verified_image_stems(images)
    # Issue #284 keeps Real-ESRGAN in one dedicated all-pages process which
    # exits before the verified page-local HOMR workers begin.
    from .dense_orchestrator_batch_sr import run_detection_step as run_verified

    return run_verified(
        config,
        images,
        page_ids,
        run_id,
        run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )
