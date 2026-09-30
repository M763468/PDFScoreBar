"""Compatibility shim for the pre-#100 dense orchestrator module name."""

from .dense_orchestrator import DetectorOrchestrator, run_detection_step

__all__ = ["DetectorOrchestrator", "run_detection_step"]
