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

DENSE_ROUTE_NAME = "dense_full_pipeline"


def _install_standard_detector_hooks() -> None:
    from .connector_artifacts import (
        install_homr_connector_artifact_capture,
        install_homr_skip_existing_guard,
    )

    install_homr_connector_artifact_capture()
    install_homr_skip_existing_guard()


def _detector_route(config: Dict[str, Any]) -> str:
    det_cfg = get_nested(config, "detection", default={}) or {}
    return str(det_cfg.get("detector_route", "standard"))


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
    """Route the public orchestrator constructor by the configured detector route."""

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
        if _detector_route(config) == DENSE_ROUTE_NAME:
            _validate_verified_image_stems(images)
            from .restored_orchestrator import DetectorOrchestrator as VerifiedDetectorOrchestrator

            return VerifiedDetectorOrchestrator(
                config=config,
                images=images,
                run_id=run_id,
                run_dir=run_dir,
                dry_run=dry_run,
                in_memory_images=in_memory_images,
            )

        _install_standard_detector_hooks()
        from .orchestrator import DetectorOrchestrator as StandardDetectorOrchestrator

        return StandardDetectorOrchestrator(
            config,
            images,
            run_id,
            run_dir,
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
    """Dispatch standard or verified Stage E production detection."""
    if _detector_route(config) == DENSE_ROUTE_NAME:
        _validate_verified_image_stems(images)
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
