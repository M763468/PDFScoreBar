from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from tools.issue245 import run_homr_evaluator_compat as compat


class _Cuda:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _Torch:
    def __init__(self, available: bool) -> None:
        self.cuda = _Cuda(available)


class _TransformerConfig:
    def __init__(self) -> None:
        self.use_gpu_inference = False


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


def _import_module(name: str) -> Any:
    if name == "torch":
        return _Torch(True)
    if name == "homr.transformer.configs":
        return SimpleNamespace(Config=_TransformerConfig)
    raise ImportError(name)


def test_injects_gpu_argument_into_historical_processing_config_call(monkeypatch) -> None:
    downloaded_with: list[bool] = []

    def download_weights(use_gpu_inference: bool) -> None:
        downloaded_with.append(use_gpu_inference)

    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
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
    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
    )

    compat.install_homr_api_compat(evaluator)
    config = evaluator.ProcessingConfig(True, False, False, False, -1, False)

    assert config.use_gpu_inference is False


def test_leaves_legacy_processing_config_signature_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
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


def test_injects_gpu_into_legacy_load_predictions_call(monkeypatch) -> None:
    calls: list[tuple[str, bool, bool, bool]] = []

    def load_predictions(
        image_path: str,
        enable_debug: bool,
        enable_cache: bool,
        use_gpu_inference: bool,
    ) -> tuple[str, bool]:
        calls.append(
            (image_path, enable_debug, enable_cache, use_gpu_inference)
        )
        return image_path, use_gpu_inference

    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
        load_and_preprocess_predictions=load_predictions,
    )

    compat.install_homr_api_compat(evaluator)
    result = evaluator.load_and_preprocess_predictions("page.png", False, True)

    assert result == ("page.png", True)
    assert calls == [("page.png", False, True, True)]
    assert (
        evaluator._issue245_load_predictions_mode
        == "gpu_argument_injected_when_missing"
    )


def test_preserves_explicit_load_predictions_gpu_argument(monkeypatch) -> None:
    calls: list[bool] = []

    def load_predictions(
        image_path: str,
        enable_debug: bool,
        enable_cache: bool,
        use_gpu_inference: bool,
    ) -> None:
        del image_path, enable_debug, enable_cache
        calls.append(use_gpu_inference)

    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
        load_and_preprocess_predictions=load_predictions,
    )

    compat.install_homr_api_compat(evaluator)
    evaluator.load_and_preprocess_predictions("page.png", False, True, False)

    assert calls == [False]


def test_injects_transformer_config_into_legacy_parse_staffs_call(monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []

    def parse_staffs(
        debug: object,
        staffs: list[object],
        image: object,
        config: _TransformerConfig,
        selected_staff: int = -1,
    ) -> list[object]:
        del debug, staffs, image
        calls.append((selected_staff, config.use_gpu_inference))
        return []

    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
        parse_staffs=parse_staffs,
    )

    compat.install_homr_api_compat(evaluator)
    result = evaluator.parse_staffs(object(), [], object(), selected_staff=-1)

    assert result == []
    assert calls == [(-1, True)]
    assert (
        evaluator._issue245_parse_staffs_mode
        == "transformer_config_injected_when_missing"
    )


def test_preserves_explicit_parse_staffs_config(monkeypatch) -> None:
    explicit_config = _TransformerConfig()
    explicit_config.use_gpu_inference = False
    calls: list[bool] = []

    def parse_staffs(
        debug: object,
        staffs: list[object],
        image: object,
        config: _TransformerConfig,
        selected_staff: int = -1,
    ) -> list[object]:
        del debug, staffs, image, selected_staff
        calls.append(config.use_gpu_inference)
        return []

    monkeypatch.setattr(compat.importlib, "import_module", _import_module)
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: None,
        ProcessingConfig=_CurrentProcessingConfig,
        parse_staffs=parse_staffs,
    )

    compat.install_homr_api_compat(evaluator)
    evaluator.parse_staffs(object(), [], object(), explicit_config)

    assert calls == [False]
