"""Resolve the externally distributed OMR-DLN measure detector model."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

MODEL_ENVIRONMENT_VARIABLE = "OMR_DLN_MODEL_PATH"
MODEL_RELATIVE_PATH = Path("external/omr_dln/models/public_models/YOLOv8m_Measures.pt")
OFFICIAL_OMR_REPOSITORY = "https://github.com/dmgonzalez8/OMR"
OFFICIAL_MODEL_FOLDER = (
    "https://drive.google.com/drive/folders/13Z64ReEJGlMnCqPkA-dcCD8tzdtvLyqO?usp=sharing"
)


def resolve_omr_dln_model_path(
    *,
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return the explicit model override or the compatible repository default."""
    configured_environment = os.environ if environment is None else environment
    override = configured_environment.get(MODEL_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override).expanduser()
    return repository_root / MODEL_RELATIVE_PATH


def omr_dln_model_missing_message(path: Path) -> str:
    """Explain how to provide the only supported OMR-DLN measure detector weight."""
    return (
        f"OMR-DLN measure detector model was not found at {path}.\n"
        "Use YOLOv8m_Measures.pt (YOLOv8m, measure detection) from the official "
        f"dmgonzalez8/OMR repository: {OFFICIAL_OMR_REPOSITORY}\n"
        f"Official model folder: {OFFICIAL_MODEL_FOLDER}\n"
        f"Set {MODEL_ENVIRONMENT_VARIABLE} to the existing read-only model path, or place it at "
        f"{MODEL_RELATIVE_PATH}. Do not substitute a generic Ultralytics or symbol model."
    )
