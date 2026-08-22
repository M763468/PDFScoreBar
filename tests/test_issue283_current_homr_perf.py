from __future__ import annotations

import json
from types import ModuleType

from src.pipeline.detection.current_homr_perf import install_current_homr_perf_attribution


def _modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    homr_main = ModuleType("fake_homr_main")
    homr_predictor = ModuleType("fake_homr_predictor")
    homr_heuristics = ModuleType("fake_homr_heuristics")
    return homr_main, homr_predictor, homr_heuristics


def test_disabled_attribution_does_not_patch_consumer(monkeypatch):
    monkeypatch.delenv("PDFSCORE_PERF_TRACE_DIR", raising=False)
    homr_main, homr_predictor, homr_heuristics = _modules()

    def predict_symbols(value: int) -> int:
        return value + 1

    homr_heuristics.predict_symbols = predict_symbols

    installed = install_current_homr_perf_attribution(homr_main, homr_predictor, homr_heuristics)

    assert installed == []
    assert homr_heuristics.predict_symbols is predict_symbols
    assert homr_heuristics.predict_symbols(4) == 5


def test_enabled_attribution_wraps_once_and_records(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_RUN", "issue283-test")
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_ROLE", "current_homr_worker")
    homr_main, homr_predictor, homr_heuristics = _modules()
    calls: list[int] = []

    def predict_symbols(value: int) -> int:
        calls.append(value)
        return value * 2

    homr_heuristics.predict_symbols = predict_symbols

    first = install_current_homr_perf_attribution(homr_main, homr_predictor, homr_heuristics)
    wrapped = homr_heuristics.predict_symbols
    second = install_current_homr_perf_attribution(homr_main, homr_predictor, homr_heuristics)

    assert first == ["current_homr.core.symbol_postprocess"]
    assert second == []
    assert homr_heuristics.predict_symbols is wrapped
    assert homr_heuristics.predict_symbols(6) == 12
    assert calls == [6]

    trace_files = list(tmp_path.glob("trace-*.jsonl"))
    assert len(trace_files) == 1
    records = [json.loads(line) for line in trace_files[0].read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["stage"] == "current_homr.core.symbol_postprocess"
    assert records[0]["success"] is True
