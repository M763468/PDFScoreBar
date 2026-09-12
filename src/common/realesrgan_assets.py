"""Resolve Real-ESRGAN weights across image-owned and local development runtimes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

WEIGHTS_ENVIRONMENT_VARIABLE = "PDFSCORE_REALESRGAN_WEIGHTS_DIR"
IMAGE_WEIGHTS_DIR = Path("/opt/pdfscore-assets/realesrgan")
SUPPORTED_MODELS = frozenset({"RealESRGAN_x2plus", "RealESRGAN_x4plus"})


def resolve_realesrgan_weight(
    model_name: str,
    *,
    project_root: Path,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return the configured image-owned weight or the legacy local checkout path."""
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported Real-ESRGAN model: {model_name}")

    configured_environment = os.environ if environment is None else environment
    configured_dir = configured_environment.get(WEIGHTS_ENVIRONMENT_VARIABLE)
    if configured_dir:
        return Path(configured_dir).expanduser() / f"{model_name}.pth"

    image_weight = IMAGE_WEIGHTS_DIR / f"{model_name}.pth"
    if image_weight.is_file():
        return image_weight

    return project_root / "external" / "realesrgan" / "weights" / f"{model_name}.pth"
