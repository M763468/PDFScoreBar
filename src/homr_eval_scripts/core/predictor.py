"""Module alias preserving predictor monkeypatch and class identity for old consumers."""

import sys

from src.homr_runtime import predictor as _runtime

sys.modules[__name__] = _runtime
