from pathlib import Path

import pytest

from src.pipeline.engine_contract import ProgressEvent, ProgressKind
from src.pipeline.main import run_pipeline


class _SuccessfulOrchestrator:
    telemetry_seen = object()

    def __init__(self, **kwargs):
        type(self).telemetry_seen = kwargs.get("telemetry")
        self.run_dir = kwargs["run_dir"]

    def run(self, page_limit=None):
        return self.run_dir


class _FailingOrchestrator(_SuccessfulOrchestrator):
    def run(self, page_limit=None):
        raise ValueError("pipeline failed")


class _ConstructorFailingOrchestrator:
    def __init__(self, **kwargs):
        raise ValueError("constructor failed")


def _patch_minimal_pipeline(monkeypatch, orchestrator_type):
    monkeypatch.setattr(
        "src.pipeline.main.load_yaml",
        lambda path: {"run": {}, "steps": {}},
    )
    monkeypatch.setattr("src.pipeline.main.PipelineOrchestrator", orchestrator_type)
    monkeypatch.setattr("src.pipeline.utils.images.clear_image_cache", lambda: None)


def test_run_pipeline_default_path_does_not_construct_telemetry(monkeypatch, tmp_path):
    _patch_minimal_pipeline(monkeypatch, _SuccessfulOrchestrator)

    result = run_pipeline(
        Path("unused.yaml"),
        run_id="job-default",
        output_root=tmp_path,
    )

    assert result == tmp_path / "job-default"
    assert _SuccessfulOrchestrator.telemetry_seen is None


def test_run_pipeline_emits_terminal_success_and_summary(monkeypatch, tmp_path):
    _patch_minimal_pipeline(monkeypatch, _SuccessfulOrchestrator)
    events: list[ProgressEvent] = []
    summary_path = tmp_path / "telemetry.json"

    result = run_pipeline(
        Path("unused.yaml"),
        run_id="job-success",
        output_root=tmp_path,
        on_progress=events.append,
        telemetry_summary_path=summary_path,
    )

    assert result == tmp_path / "job-success"
    assert [event.kind for event in events] == [
        ProgressKind.JOB_STARTED,
        ProgressKind.JOB_SUCCEEDED,
    ]
    assert summary_path.is_file()
    assert "pdfscorebar.engine.telemetry_summary.v1" in summary_path.read_text()


def test_run_pipeline_emits_terminal_failure_without_swallowing_exception(
    monkeypatch,
    tmp_path,
):
    _patch_minimal_pipeline(monkeypatch, _FailingOrchestrator)
    events: list[ProgressEvent] = []

    with pytest.raises(ValueError, match="pipeline failed"):
        run_pipeline(
            Path("unused.yaml"),
            run_id="job-failure",
            output_root=tmp_path,
            on_progress=events.append,
        )

    assert [event.kind for event in events] == [
        ProgressKind.JOB_STARTED,
        ProgressKind.JOB_FAILED,
    ]


def test_run_pipeline_emits_terminal_failure_when_orchestrator_construction_fails(
    monkeypatch,
    tmp_path,
):
    _patch_minimal_pipeline(monkeypatch, _ConstructorFailingOrchestrator)
    events: list[ProgressEvent] = []

    with pytest.raises(ValueError, match="constructor failed"):
        run_pipeline(
            Path("unused.yaml"),
            run_id="job-constructor-failure",
            output_root=tmp_path,
            on_progress=events.append,
        )

    assert [event.kind for event in events] == [
        ProgressKind.JOB_STARTED,
        ProgressKind.JOB_FAILED,
    ]


def test_resource_sampling_keeps_default_summary_in_run_directory(monkeypatch, tmp_path):
    _patch_minimal_pipeline(monkeypatch, _SuccessfulOrchestrator)

    result = run_pipeline(
        Path("unused.yaml"),
        run_id="job-resources",
        output_root=tmp_path,
        sample_resources=True,
        resource_sample_interval_seconds=0.01,
    )

    summary_path = result / "telemetry.json"
    assert summary_path.is_file()
    summary_text = summary_path.read_text()
    assert "resource_sample_count" in summary_text
    assert "pdfscorebar.engine.telemetry_summary.v1" in summary_text
