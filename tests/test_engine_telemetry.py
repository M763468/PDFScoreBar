import pytest

from src.pipeline.engine_contract import (
    JobResult,
    JobStatus,
    ProgressEvent,
    ProgressKind,
    validate_progress_sequence,
)
from src.pipeline.engine_telemetry import TELEMETRY_SUMMARY_SCHEMA, TelemetryRecorder


def _provenance() -> dict[str, str]:
    return {
        "engine_version": "0.1.0",
        "pipeline_version": "dense-v1",
        "source_commit": "abc123",
    }


def test_progress_event_telemetry_fields_round_trip_deterministically():
    event = ProgressEvent(
        job_id="job-1",
        sequence=3,
        kind=ProgressKind.STAGE_COMPLETED,
        stage_id="score_detection",
        completed_units=2,
        total_units=2,
        unit="page",
        elapsed_ms=1250,
        detail_code="detection.completed",
    )

    restored = ProgressEvent.from_json(event.to_json())

    assert restored == event
    assert restored.to_dict()["elapsed_ms"] == 1250
    assert restored.to_dict()["detail_code"] == "detection.completed"


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (JobStatus.SUCCEEDED, ProgressKind.JOB_SUCCEEDED),
        (JobStatus.REVIEW_REQUIRED, ProgressKind.JOB_REVIEW_REQUIRED),
        (JobStatus.FAILED, ProgressKind.JOB_FAILED),
        (JobStatus.CANCELLED, ProgressKind.JOB_CANCELLED),
    ],
)
def test_recorder_terminal_kind_matches_job_status(status, kind):
    events = []
    recorder = TelemetryRecorder("job-1", on_progress=events.append)

    recorder.start_job()
    with recorder.stage("score_detection", completed_units=1, total_units=1, unit="page"):
        recorder.progress(
            "score_detection",
            page_number=1,
            completed_units=1,
            total_units=1,
            unit="page",
        )
    terminal = recorder.terminal(status)

    validate_progress_sequence(events)
    assert terminal.kind is kind
    assert terminal.terminal is True
    assert events[-1] == terminal
    assert events[0].kind is ProgressKind.JOB_STARTED
    assert any(event.elapsed_ms is not None for event in events)


def test_recorder_rejects_events_after_terminal():
    recorder = TelemetryRecorder("job-1")
    recorder.start_job()
    recorder.terminal(JobStatus.SUCCEEDED)

    with pytest.raises(RuntimeError, match="after terminal"):
        recorder.progress("numbering")


def test_progress_sink_failure_is_isolated_from_engine_execution():
    attempts = []

    def broken_sink(event: ProgressEvent) -> None:
        attempts.append(event.sequence)
        raise RuntimeError("sink unavailable")

    recorder = TelemetryRecorder("job-1", on_progress=broken_sink)

    recorder.start_job()
    with recorder.stage("numbering"):
        pass
    recorder.terminal(JobStatus.SUCCEEDED)

    assert attempts == [0, 1, 2, 3]
    assert recorder.job_resources()["progress_sink_error_count"] == 4


def test_aborted_stage_is_retained_without_false_stage_completed_event():
    events = []
    recorder = TelemetryRecorder("job-1", on_progress=events.append)
    recorder.start_job()

    with pytest.raises(ValueError, match="boom"):
        with recorder.stage("measure_construction"):
            raise ValueError("boom")

    recorder.terminal(JobStatus.FAILED)
    summary = recorder.summary()

    assert [event.kind for event in events] == [
        ProgressKind.JOB_STARTED,
        ProgressKind.STAGE_STARTED,
        ProgressKind.JOB_FAILED,
    ]
    assert summary["stage_spans"][0]["state"] == "aborted"


def test_summary_resources_are_job_result_compatible_without_sampling():
    recorder = TelemetryRecorder("job-1")
    recorder.start_job()
    with recorder.stage("artifact_materialization"):
        pass
    recorder.terminal(JobStatus.SUCCEEDED)

    summary = recorder.summary()
    result = JobResult(
        job_id="job-1",
        status=JobStatus.SUCCEEDED,
        provenance=_provenance(),
        pages={"requested": 1, "processed": 1, "skipped": 0},
        resources=recorder.job_resources(),
    )

    assert summary["schema"] == TELEMETRY_SUMMARY_SCHEMA
    assert summary["job_id"] == "job-1"
    assert summary["stage_spans"][0]["stage_id"] == "artifact_materialization"
    assert result.resources["wall_time_seconds"] >= 0
    assert result.resources["progress_sink_error_count"] == 0
