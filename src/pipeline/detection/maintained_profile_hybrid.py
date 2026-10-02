"""Maintained original-page baseline and current-x4 support workflow."""

from typing import Any

from .maintained_profile import run_homr_profile
from .profile_sources import ProfileHybridDetector
from .profile_sources_batch_sr import BatchSRProfileHybridDetector


class VerifiedProfileHybridDetector(ProfileHybridDetector):
    source_worker_module = "src.pipeline.detection.maintained_source_page_worker"

    def _run_homr_profile(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return run_homr_profile(*args, **kwargs)


class BatchSRVerifiedProfileHybridDetector(
    BatchSRProfileHybridDetector, VerifiedProfileHybridDetector
):
    source_worker_module = "src.pipeline.detection.maintained_source_page_worker"

    def _run_homr_profile(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return run_homr_profile(*args, **kwargs)
