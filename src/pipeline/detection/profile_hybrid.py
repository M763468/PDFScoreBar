"""Historical/compatibility two-HOMR workflow with the general profile dispatcher."""

from typing import Any

from .homr_profile import run_homr_profile
from .profile_sources import ProfileHybridDetector


class VerifiedProfileHybridDetector(ProfileHybridDetector):
    def _run_homr_profile(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return run_homr_profile(*args, **kwargs)
