from pathlib import Path

import pytest

from src.pipeline.engine_contract import ProgressEvent, ProgressKind
from src.pipeline.engine_telemetry import TelemetryRecorder
from src.pipeline.main import run_pipeline
from src.pipeline.orchestrator import PipelineOrchestrator


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


def _assert_input_validation_aborted(events: list[ProgressEvent]) -> None:
    assert [(event.kind, event.stage_id) for event in events] == [
        (ProgressKind.JOB_STARTED, "job"),
        (ProgressKind.STAGE_STARTED, "input_validation"),
    ]


def test_input_validation_does_not_complete_when_pdf_path_is_missing(tmp_path):
    events: list[ProgressEvent] = []
    telemetry = TelemetryRecorder("job-invalid-pdf", on_progress=events.append)
    orchestrator = PipelineOrchestrator(
        config={"steps": {"pdf_to_images": True}, "inputs": {}},
        run_id="job-invalid-pdf",
        run_dir=tmp_path,
        telemetry=telemetry,
    )

    with pytest.raises(ValueError, match="inputs.pdf_path"):
        orchestrator.run()

    _assert_input_validation_aborted(events)
    span = telemetry.summary()["stage_spans"][0]
    assert span["stage_id"] == "input_validation"
    assert span["state"] == "aborted"


def test_input_validation_does_not_complete_when_external_images_are_missing(tmp_path):
    events: list[ProgressEvent] = []
    telemetry = TelemetryRecorder("job-missing-images", on_progress=events.append)
    orchestrator = PipelineOrchestrator(
        config={
            "steps": {"pdf_to_images": False},
            "inputs": {
                "pdf_to_images": {
                    "output_dir": str(tmp_path / "missing-images"),
                    "image_glob": "page_*.png",
                }
            },
        },
        run_id="job-missing-images",
        run_dir=tmp_path / "run",
        telemetry=telemetry,
    )

    with pytest.raises(FileNotFoundError, match="No images found"):
        orchestrator.run()

    _assert_input_validation_aborted(events)


@pytest.mark.parametrize("input_key", ["measure_overrides", "movement_boundaries"])
def test_input_validation_does_not_complete_for_malformed_structured_input(
    tmp_path,
    input_key,
):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "page_001.png").write_bytes(b"placeholder")
    malformed = tmp_path / f"{input_key}.json"
    malformed.write_text("{not-json", encoding="utf-8")

    events: list[ProgressEvent] = []
    telemetry = TelemetryRecorder(f"job-{input_key}", on_progress=events.append)
    orchestrator = PipelineOrchestrator(
        config={
            "steps": {"pdf_to_images": False},
            "inputs": {
                "pdf_to_images": {
                    "output_dir": str(image_dir),
                    "image_glob": "page_*.png",
                },
                input_key: str(malformed),
            },
        },
        run_id=f"job-{input_key}",
        run_dir=tmp_path / "run",
        telemetry=telemetry,
    )

    with pytest.raises(ValueError):
        orchestrator.run()

    _assert_input_validation_aborted(events)
