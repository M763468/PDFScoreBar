"""Verified dense-route orchestrator using the Issue #284 batch-SR profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .profile_hybrid_batch_sr import BatchSRVerifiedProfileHybridDetector
from .restored_orchestrator import DetectorOrchestrator as BaseDetectorOrchestrator


class DetectorOrchestrator(BaseDetectorOrchestrator):
    """Keep the accepted dense route unchanged except for current-x4 SR scheduling."""

    def _run_hybrid_detection(self) -> Dict[str, Any]:
        detector = BatchSRVerifiedProfileHybridDetector(
            det_cfg=self.det_cfg,
            images=self.images,
            run_id=self.run_id,
            project_root=Path(__file__).resolve().parents[3],
            dry_run=self.dry_run,
            skip_existing=self.skip_existing,
            in_memory_images=self.in_memory_images,
            profile_name=str(self.homr_profile),
        )
        return detector.run()


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
    """Run the verified Stage E detector with a dedicated all-pages SR phase."""
    if len(images) != len(page_ids):
        raise ValueError("images/page_ids length mismatch")
    orchestrator = DetectorOrchestrator(
        config=config,
        images=images,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )
    return orchestrator.run_detection()
