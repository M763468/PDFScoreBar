import pytest

pytest.importorskip("torch")
pytest.importorskip("torchvision")

import torch

from src.pipeline.steps.cnn_scoring import (
    _build_model,
    _infer_model_architecture,
    _load_model,
    _resolve_model_path,
)


def test_resolve_model_path_requires_existing_file(tmp_path):
    missing_model = tmp_path / "missing_model.pth"

    with pytest.raises(FileNotFoundError) as exc_info:
        _resolve_model_path(missing_model)

    message = str(exc_info.value)
    assert "CNN model file not found" in message
    assert "detection.cnn_model_path" in message
    assert str(missing_model) in message


def test_resolve_model_path_rejects_directory(tmp_path):
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir()

    with pytest.raises(FileNotFoundError) as exc_info:
        _resolve_model_path(model_dir)

    message = str(exc_info.value)
    assert "CNN model path is not a file" in message
    assert "detection.cnn_model_path" in message
    assert str(model_dir) in message


def test_resolve_model_path_accepts_existing_file(tmp_path):
    model_path = tmp_path / "model.pth"
    model_path.write_bytes(b"placeholder")

    assert _resolve_model_path(model_path) == model_path


def test_resolve_model_path_accepts_existing_file_string(tmp_path):
    model_path = tmp_path / "model.pth"
    model_path.write_bytes(b"placeholder")

    assert _resolve_model_path(str(model_path)) == model_path


def test_resolve_model_path_rejects_none():
    with pytest.raises(ValueError) as exc_info:
        _resolve_model_path(None)

    message = str(exc_info.value)
    assert "CNN model path is not configured" in message
    assert "detection.cnn_model_path" in message


def test_infer_model_architecture_preserves_resnet18_compatibility():
    state_dict = {
        "fc.weight": torch.empty(1, 512),
        "fc.bias": torch.empty(1),
    }

    assert _infer_model_architecture(state_dict) == "resnet18"


def test_infer_model_architecture_supports_efficientnet_b0():
    state_dict = {
        "classifier.1.weight": torch.empty(1, 1280),
        "classifier.1.bias": torch.empty(1),
    }

    assert _infer_model_architecture(state_dict) == "efficientnet_b0"


def test_infer_model_architecture_rejects_unknown_checkpoint():
    with pytest.raises(ValueError, match="Unable to infer CNN model architecture"):
        _infer_model_architecture({"unknown.weight": torch.empty(1)})


def test_build_efficientnet_b0_has_binary_classifier():
    model = _build_model("efficientnet_b0")

    assert model.classifier[1].out_features == 1


def test_load_model_accepts_efficientnet_b0_state_dict(tmp_path):
    checkpoint = tmp_path / "efficientnet_b0.pth"
    expected = _build_model("efficientnet_b0")
    torch.save(expected.state_dict(), checkpoint)

    loaded = _load_model(checkpoint, torch.device("cpu"))

    assert loaded.classifier[1].out_features == 1
    assert loaded.training is False
