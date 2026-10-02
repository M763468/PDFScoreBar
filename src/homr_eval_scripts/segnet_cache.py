"""Compatibility alias for the production-owned Segnet cache."""

import sys

from src.homr_runtime import segnet_cache as _runtime

sys.modules[__name__] = _runtime
