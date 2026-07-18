"""Resolve the externally distributed OMR-DLN measure detector model."""

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
    """Explain how to install the only supported OMR-DLN measure detector weight."""
    return (
        f"OMR-DLN measure detector model was not found at {path}.\n"
        "Download YOLOv8m_Measures.pt (YOLOv8m, measure detection) from the official "
        f"dmgonzalez8/OMR repository: {OFFICIAL_OMR_REPOSITORY}\n"
        f"Google Drive model folder: {OFFICIAL_MODEL_FOLDER}\n"
        "Keep the filename YOLOv8m_Measures.pt and place it at "
        f"{MODEL_RELATIVE_PATH}, or set {MODEL_ENVIRONMENT_VARIABLE} to an existing "
        "read-only shared model path. Do not substitute a generic Ultralytics or symbol model."
    )
