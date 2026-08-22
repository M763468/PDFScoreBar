import json
import sys
import types

import pytest

from src.pipeline import perf_trace


def test_disabled_trace_writes_no_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFSCORE_PERF_TRACE_DIR", raising=False)
    with perf_trace.span("disabled"):
        pass
    assert list(tmp_path.iterdir()) == []


def test_enabled_trace_records_span_and_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_DIR", str(tmp_path))
    token = perf_trace.set_context(run_id="r1", page="page_013", process_role="test")
    try:
        with perf_trace.span("expected.stage", call_count=2, bytes_count=11):
            pass
    finally:
        perf_trace.reset_context(token)
    rows = [
        json.loads(line)
        for line in (tmp_path / f"trace-{__import__('os').getpid()}.jsonl").read_text().splitlines()
    ]
    assert rows[0]["stage"] == "expected.stage"
    assert rows[0]["run_id"] == "r1"
    assert rows[0]["page"] == "page_013"
    assert rows[0]["call_count"] == 2
    assert rows[0]["bytes"] == 11
    assert rows[0]["success"] is True


def test_exception_closes_span_as_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        with perf_trace.span("failing.stage"):
            raise ValueError("boom")
    path = next(tmp_path.glob("trace-*.jsonl"))
    row = json.loads(path.read_text().strip())
    assert row["success"] is False
    assert "ValueError" in row["error"]
    assert row["duration_sec"] >= 0


def test_cuda_span_synchronizes_before_and_after_operation(monkeypatch, tmp_path):
    calls = []

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def synchronize():
            calls.append("sync")

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=FakeCuda()))
    monkeypatch.setenv("PDFSCORE_PERF_TRACE_DIR", str(tmp_path))
    with perf_trace.span("cuda.stage", cuda=True):
        calls.append("operation")
    assert calls == ["sync", "operation", "sync"]
