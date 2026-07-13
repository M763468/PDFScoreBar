from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tools.issue245 import run_homr_evaluator_compat as compat


class _Input:
    def __init__(self, name: str, value_type: str = "tensor(float)") -> None:
        self.name = name
        self.type = value_type


class _Output:
    def __init__(self, name: str) -> None:
        self.name = name


class _Session:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def get_inputs(self) -> list[_Input]:
        return [_Input("input")]

    def get_outputs(self) -> list[_Output]:
        return [_Output("output")]

    def run(self, outputs: list[str], inputs: dict[str, Any]) -> list[str]:
        self.calls.append((outputs, inputs))
        return ["ok"]


class _LegacyCachedSegnet:
    def __init__(self, model_path: str, use_gpu: bool) -> None:
        self.model_path = model_path
        self.use_gpu = use_gpu


class _CurrentCachedSegnet:
    def __init__(self, use_gpu: bool) -> None:
        self.use_gpu = use_gpu


def test_adapts_legacy_cache_constructor_for_current_homr(monkeypatch) -> None:
    session = _Session()
    calls: list[tuple[str, bool]] = []

    def get_session(model_path: str, use_gpu: bool) -> _Session:
        calls.append((model_path, use_gpu))
        return session

    cache_module = SimpleNamespace(
        CachedSegnet=_LegacyCachedSegnet,
        _get_session=get_session,
    )
    config_module = SimpleNamespace(
        segnet_path_onnx="segnet-fp32.onnx",
        segnet_path_onnx_fp16="segnet-fp16.onnx",
    )

    def import_module(name: str) -> Any:
        if name == "homr_eval_scripts.segnet_cache":
            return cache_module
        if name == "homr.segmentation.config":
            return config_module
        raise ImportError(name)

    monkeypatch.setattr(compat.importlib, "import_module", import_module)

    mode = compat._install_segnet_cache_compat()
    cached = cache_module.CachedSegnet(True)

    assert mode == "one_or_two_argument_constructor_injected"
    assert calls == [("segnet-fp16.onnx", True)]
    assert cached.run("payload") == "ok"
    assert session.calls == [(["output"], {"input": "payload"})]


def test_preserves_legacy_two_argument_cache_call(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def get_session(model_path: str, use_gpu: bool) -> _Session:
        calls.append((model_path, use_gpu))
        return _Session()

    cache_module = SimpleNamespace(
        CachedSegnet=_LegacyCachedSegnet,
        _get_session=get_session,
    )

    monkeypatch.setattr(
        compat.importlib,
        "import_module",
        lambda name: cache_module
        if name == "homr_eval_scripts.segnet_cache"
        else (_ for _ in ()).throw(ImportError(name)),
    )

    compat._install_segnet_cache_compat()
    cache_module.CachedSegnet("explicit.onnx", False)

    assert calls == [("explicit.onnx", False)]


def test_leaves_current_cache_constructor_unchanged(monkeypatch) -> None:
    cache_module = SimpleNamespace(
        CachedSegnet=_CurrentCachedSegnet,
        _get_session=lambda model_path, use_gpu: None,
    )
    monkeypatch.setattr(
        compat.importlib,
        "import_module",
        lambda name: cache_module
        if name == "homr_eval_scripts.segnet_cache"
        else (_ for _ in ()).throw(ImportError(name)),
    )

    original = cache_module.CachedSegnet
    mode = compat._install_segnet_cache_compat()

    assert mode == "native_one_or_two_argument_constructor"
    assert cache_module.CachedSegnet is original
