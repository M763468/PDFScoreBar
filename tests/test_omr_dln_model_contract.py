from pathlib import Path

from src.pipeline.detection.omr_dln_model import (
    MODEL_ENVIRONMENT_VARIABLE,
    MODEL_RELATIVE_PATH,
    OFFICIAL_MODEL_FOLDER,
    OFFICIAL_OMR_REPOSITORY,
    omr_dln_model_missing_message,
    resolve_omr_dln_model_path,
)


def test_omr_dln_model_uses_repository_default() -> None:
    repository_root = Path("/workspace")

    assert (
        resolve_omr_dln_model_path(
            repository_root=repository_root,
            environment={},
        )
        == repository_root / MODEL_RELATIVE_PATH
    )


def test_omr_dln_model_accepts_shared_override() -> None:
    shared_model = Path("/models/YOLOv8m_Measures.pt")

    assert (
        resolve_omr_dln_model_path(
            repository_root=Path("/workspace"),
            environment={MODEL_ENVIRONMENT_VARIABLE: str(shared_model)},
        )
        == shared_model
    )


def test_missing_model_message_identifies_only_supported_weight() -> None:
    model_path = Path("/missing/YOLOv8m_Measures.pt")
    message = omr_dln_model_missing_message(model_path)

    assert str(model_path) in message
    assert "YOLOv8m_Measures.pt" in message
    assert MODEL_ENVIRONMENT_VARIABLE in message
    assert OFFICIAL_OMR_REPOSITORY in message
    assert OFFICIAL_MODEL_FOLDER in message
    assert "generic Ultralytics" in message
