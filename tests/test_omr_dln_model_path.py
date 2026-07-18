from src.pipeline.detection.omr_dln_model import (
    MODEL_ENVIRONMENT_VARIABLE,
    MODEL_RELATIVE_PATH,
    OFFICIAL_MODEL_FOLDER,
    OFFICIAL_OMR_REPOSITORY,
    omr_dln_model_missing_message,
    resolve_omr_dln_model_path,
)


def test_resolve_omr_dln_model_path_uses_repository_compatible_default(tmp_path):
    assert resolve_omr_dln_model_path(repository_root=tmp_path, environment={}) == (
        tmp_path / MODEL_RELATIVE_PATH
    )


def test_resolve_omr_dln_model_path_honors_shared_model_override(tmp_path):
    shared_model = tmp_path / "shared" / "YOLOv8m_Measures.pt"
    assert (
        resolve_omr_dln_model_path(
            repository_root=tmp_path,
            environment={MODEL_ENVIRONMENT_VARIABLE: str(shared_model)},
        )
        == shared_model
    )


def test_omr_dln_model_missing_message_contains_official_bootstrap_instructions(tmp_path):
    message = omr_dln_model_missing_message(tmp_path / "missing.pt")

    assert MODEL_ENVIRONMENT_VARIABLE in message
    assert OFFICIAL_OMR_REPOSITORY in message
    assert OFFICIAL_MODEL_FOLDER in message
    assert "YOLOv8m_Measures.pt" in message
