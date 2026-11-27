"""Minimal Real-ESRGAN inference runtime (RRDBNet + tiled upsampler).

Replaces the ``basicsr`` / ``realesrgan`` distributions in the production image
(Issue #533). See ``README.md`` in this directory for provenance and licenses.
"""

from src.third_party.realesrgan_sr.rrdbnet import RRDBNet
from src.third_party.realesrgan_sr.upsampler import RealESRGANer

__all__ = ["RRDBNet", "RealESRGANer"]
