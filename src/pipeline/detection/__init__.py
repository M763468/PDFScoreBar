"""Detection package providing barlines detection orchestration."""

from .default_route import run_detection_step
from .utils import resolve_barlines_and_masks_config, resolve_paths_from_detection

__all__ = [
    "DetectorOrchestrator",
    "run_detection_step",
    "resolve_barlines_and_masks_config",
    "resolve_paths_from_detection",
]


def __getattr__(name: str):
    if name == "DetectorOrchestrator":
        from .orchestrator import DetectorOrchestrator

        return DetectorOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
