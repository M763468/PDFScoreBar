import pytest

pytest.importorskip("torch")
pytest.importorskip("torchvision")

import torch
from torchvision import models

from src.pipeline.detection.restored_orchestrator import _validate_verified_cnn_checkpoint
from src.pipeline.steps.cnn_scoring import _build_model, _load_model


def _save_resnet18_checkpoint(path):
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 1)
    torch.save(model.state_dict(), path)


def _save_efficientnet_b0_checkpoint(path):
    model = _build_model("efficientnet_b0")
    torch.save(model.state_dict(), path)


def test_shared_loader_keeps_standard_resnet18_checkpoint_support(tmp_path):
    checkpoint = tmp_path / "resnet18.pth"
    _save_resnet18_checkpoint(checkpoint)

    loaded = _load_model(checkpoint, torch.device("cpu"))

    assert loaded.fc.out_features == 1
    assert loaded.training is False


def test_verified_route_rejects_legacy_resnet18_checkpoint(tmp_path):
    checkpoint = tmp_path / "resnet18.pth"
    _save_resnet18_checkpoint(checkpoint)

    with pytest.raises(ValueError, match="requires an EfficientNet-B0 CNN checkpoint"):
        _validate_verified_cnn_checkpoint(checkpoint)


def test_verified_route_accepts_d27_architecture(tmp_path):
    checkpoint = tmp_path / "efficientnet_b0.pth"
    _save_efficientnet_b0_checkpoint(checkpoint)

    _validate_verified_cnn_checkpoint(checkpoint)
