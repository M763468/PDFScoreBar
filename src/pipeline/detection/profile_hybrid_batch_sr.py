"""Historical/compatibility hybrid workflow with dedicated batch SR."""

from typing import Any

from .profile_hybrid import VerifiedProfileHybridDetector, run_homr_profile
from .profile_sources_batch_sr import BatchSRProfileHybridDetector


class BatchSRVerifiedProfileHybridDetector(
    BatchSRProfileHybridDetector, VerifiedProfileHybridDetector
):
    def _run_homr_profile(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return run_homr_profile(*args, **kwargs)
