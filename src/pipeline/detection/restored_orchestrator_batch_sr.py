"""Compatibility shim for the pre-#100 batch-SR dense orchestrator module name."""

from .dense_orchestrator_batch_sr import DetectorOrchestrator, run_detection_step

__all__ = ["DetectorOrchestrator", "run_detection_step"]
