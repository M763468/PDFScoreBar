from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from tools.issue245 import run_homr_evaluator_compat as compat


class _Cuda:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _Torch:
    def __init__(self, available: bool) -> None:
        self.cuda = _Cuda(available)


@dataclass
class _CurrentProcessingConfig:
    enable_debug: bool
    enable_cache: bool
    write_staff_positions: bool
    read_staff_positions: bool
    selected_staff: int
    use_gpu_inference: bool


@dataclass
class _LegacyProcessingConfig:
    enable_debug: bool
    enable_cache: bool
    write_staff_positions: bool
    read_staff_positions: bool
    selected_staff: int


def test_injects_gpu_argument_into_historical_processing_config_call(monkeypatch) -> None:
    downloaded_with: list[bool] = []

    def download_weights(use_gpu_inference: bool) -> None:
        downloaded_with.append(use_gpu_inference)

    monkeypatch.setattr(
        compat.importlib,
        "import_module",
        lambda name: _Torch(name == "torch"),
    )
    evaluator = SimpleNamespace(
        download_weights=download_weights,
        ProcessingConfig=_CurrentProcessingConfig,
    )

    use_gpu = compat.install_homr_api_compat(evaluator)
    evaluator.download_weights()
    config = evaluator.ProcessingConfig(True, False, False, False, -1)

    assert use_gpu is True
    assert downloaded_with == [True]
    assert config.use_gpu_inference is True
    assert (
        evaluator._issue245_processing_config_mode
        == "gpu_argument_injected_when_missing"
    )


def test_preserves_explicit_processing_config_gpu_argument(monkeypatch) -> None:
    monkeypatch.setattr(
        compat.importlib,
        "import_module",
        lambda name: _Torch(name == "torch"),
    )
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
    )

    compat.install_homr_api_compat(evaluator)
    config = evaluator.ProcessingConfig(True, False, False, False, -1, False)

    assert config.use_gpu_inference is False


def test_leaves_legacy_processing_config_signature_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(
        compat.importlib,
        "import_module",
        lambda name: _Torch(name == "torch"),
    )
    evaluator = SimpleNamespace(
        download_weights=lambda: None,
        ProcessingConfig=_LegacyProcessingConfig,
    )

    compat.install_homr_api_compat(evaluator)
    config = evaluator.ProcessingConfig(True, False, False, False, -1)

    assert isinstance(config, _LegacyProcessingConfig)
    assert evaluator._issue245_download_weights_mode == "native_zero_argument"
    assert (
        evaluator._issue245_processing_config_mode == "native_without_gpu_argument"
    )
