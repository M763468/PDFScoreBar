from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("torchvision")

from src.pipeline.steps.cnn_scoring import _resolve_model_path


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
