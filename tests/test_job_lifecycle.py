import pytest

from src.pipeline.engine_contract import ErrorCategory, JobStatus
from src.pipeline.engine_lifecycle import (
    CancellationToken,
    ExecutionControl,
    ExecutionDeadline,
    JobCancelled,
    JobDeadlineExceeded,
    LifecycleControlError,
    classify_control_error,
)


def test_cancellation_token_is_idempotent_and_preserves_first_reason():
    token = CancellationToken()

    assert token.cancel("caller requested stop") is True
    assert token.cancel("later replacement") is False
    assert token.cancelled is True
    assert token.reason == "caller requested stop"


def test_execution_control_raises_cancelled_with_stage_and_reason():
    token = CancellationToken()
    control = ExecutionControl(cancellation=token)
    token.cancel("review no longer needed")

    with pytest.raises(JobCancelled, match="review no longer needed") as exc_info:
        control.checkpoint(stage_id="artifact_materialization")

    assert exc_info.value.stage_id == "artifact_materialization"


def test_execution_deadline_is_monotonic_and_reports_remaining_time():
    deadline = ExecutionDeadline.after(10.0, now=100.0)

    assert deadline.remaining_seconds(now=103.5) == pytest.approx(6.5)
    assert deadline.expired(now=109.999) is False
    assert deadline.expired(now=110.0) is True
    assert deadline.remaining_seconds(now=111.0) == 0.0


def test_execution_deadline_rejects_non_positive_duration():
    with pytest.raises(ValueError, match="must be > 0"):
        ExecutionDeadline.after(0.0, now=100.0)


def test_execution_control_raises_deadline_exceeded_with_stage():
    control = ExecutionControl.with_timeout(5.0, now=10.0)

    control.checkpoint(stage_id="score_detection", now=14.9)
    with pytest.raises(JobDeadlineExceeded) as exc_info:
        control.checkpoint(stage_id="score_detection", now=15.0)

    assert exc_info.value.stage_id == "score_detection"


def test_explicit_cancellation_wins_when_deadline_is_also_expired():
    token = CancellationToken()
    token.cancel("caller cancelled")
    control = ExecutionControl(
        cancellation=token,
        deadline=ExecutionDeadline(deadline_monotonic=5.0),
    )

    with pytest.raises(JobCancelled):
        control.checkpoint(stage_id="numbering", now=10.0)


def test_cancelled_maps_to_normative_v1_status_and_error():
    status, error = classify_control_error(
        JobCancelled("caller reason remains diagnostic", stage_id="numbering")
    )

    assert status is JobStatus.CANCELLED
    assert error.category is ErrorCategory.CANCELLED
    assert error.code == "job_cancelled"
    assert error.retryable is False
    assert error.to_dict()["public_message"] == "The job was cancelled."
    assert "debug_context" not in error.to_dict()
    assert error.to_dict(include_debug_context=True)["debug_context"]["stage_id"] == "numbering"


def test_deadline_maps_to_failed_resource_error_and_retryable_hint():
    status, error = classify_control_error(
        JobDeadlineExceeded("deadline expired", stage_id="score_detection")
    )

    assert status is JobStatus.FAILED
    assert error.category is ErrorCategory.RESOURCE
    assert error.code == "execution_deadline_exceeded"
    assert error.retryable is True


def test_classify_control_error_rejects_unknown_subclass():
    class UnknownControlError(LifecycleControlError):
        pass

    with pytest.raises(TypeError, match="Unsupported lifecycle control error"):
        classify_control_error(UnknownControlError("unknown"))


def test_remaining_timeout_is_none_without_deadline():
    assert ExecutionControl().remaining_timeout(now=123.0) is None
