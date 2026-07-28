"""Detection package providing barlines detection orchestration."""

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


def __getattr__(name: str):
    if name in {"DetectorOrchestrator", "run_detection_step"}:
        from .orchestrator import DetectorOrchestrator, run_detection_step

        return {
            "DetectorOrchestrator": DetectorOrchestrator,
            "run_detection_step": run_detection_step,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
