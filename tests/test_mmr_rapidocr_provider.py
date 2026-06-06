import sys
import types

import pytest


def _install_import_stubs() -> None:
    sys.modules.setdefault("rapidocr_onnxruntime", types.SimpleNamespace(RapidOCR=object))


_install_import_stubs()

from src.measure_numbering import rapidocr_provider


class _DummyRapidOCR:
    calls = []

    def __init__(self, **kwargs):
        type(self).calls.append(kwargs)
        self.det = _DummySession(["CUDAExecutionProvider", "CPUExecutionProvider"])


class _DummySession:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return self._providers


def test_auto_uses_cuda_kwargs_when_cuda_provider_is_available(monkeypatch):
    _DummyRapidOCR.calls = []
    monkeypatch.setattr(rapidocr_provider, "RapidOCR", _DummyRapidOCR)
    monkeypatch.setattr(rapidocr_provider, "onnxruntime_has_cuda_provider", lambda: True)

    rapidocr_provider.create_mmr_rapidocr()

    assert _DummyRapidOCR.calls == [
        {"det_use_cuda": True, "cls_use_cuda": True, "rec_use_cuda": True}
    ]


def test_auto_keeps_default_constructor_when_cuda_provider_is_unavailable(monkeypatch):
    _DummyRapidOCR.calls = []
    monkeypatch.setattr(rapidocr_provider, "RapidOCR", _DummyRapidOCR)
    monkeypatch.setattr(rapidocr_provider, "onnxruntime_has_cuda_provider", lambda: False)

    rapidocr_provider.create_mmr_rapidocr()

    assert _DummyRapidOCR.calls == [{}]


def test_cpu_mode_keeps_default_constructor_even_when_cuda_is_available(monkeypatch):
    _DummyRapidOCR.calls = []
    monkeypatch.setattr(rapidocr_provider, "RapidOCR", _DummyRapidOCR)
    monkeypatch.setattr(rapidocr_provider, "onnxruntime_has_cuda_provider", lambda: True)

    rapidocr_provider.create_mmr_rapidocr("cpu")

    assert _DummyRapidOCR.calls == [{}]


def test_cuda_mode_warns_when_cuda_provider_is_not_confirmed(monkeypatch, caplog):
    class CpuOnlyRapidOCR:
        def __init__(self, **kwargs):
            self.det = _DummySession(["CPUExecutionProvider"])

    monkeypatch.setattr(rapidocr_provider, "RapidOCR", CpuOnlyRapidOCR)

    with caplog.at_level("WARNING"):
        rapidocr_provider.create_mmr_rapidocr("cuda")

    assert "CUDAExecutionProvider was not confirmed" in caplog.text


def test_normalize_rapidocr_provider_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unsupported MMR RapidOCR provider mode"):
        rapidocr_provider.normalize_rapidocr_provider("gpu")
