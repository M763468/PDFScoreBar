from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import fitz
import pytest

import src.pipeline.engine_executor as engine_executor_module
from src.pipeline.engine_contract import (
    CONTRACT_VERSION,
    CorrectionSet,
    ErrorCategory,
    JobRequest,
    JobStatus,
    OutputProfile,
    ProgressKind,
    validate_progress_sequence,
)
from src.pipeline.engine_executor import PipelineJobExecutor
from src.pipeline.engine_input_safety import JobSafetyPolicy


@pytest.fixture
def executor_fixture(tmp_path: Path):
    input_root = tmp_path / "inputs"
    artifact_root = tmp_path / "artifacts"
    input_root.mkdir()

    pdf_path = input_root / "score.pdf"
    document = fitz.open()
    document.new_page(width=100, height=100)
    document.save(pdf_path)
    document.close()

    config_path = tmp_path / "base.yaml"
    config_path.write_text(
        """
run:
  run_id: test
  output_root: ignored
inputs:
  pdf_to_images:
    dpi: 72
steps:
  pdf_to_images: true
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    def fake_runner(
        _config_path,
        *,
        run_id,
        output_root,
        telemetry_recorder,
        **_kwargs,
    ):
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with telemetry_recorder.stage("input_validation"):
            pass
        with telemetry_recorder.stage("artifact_materialization"):
            pass
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "page_id": "page_001",
                            "status": {
                                "page_index": 1,
                                "excluded_by_user": False,
                                "blank_page": False,
                                "staff_detect_failed": False,
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return run_dir

    def fake_review(*, review_root, **_kwargs):
        review_root = Path(review_root)
        review_root.mkdir(parents=True, exist_ok=True)
        (review_root / "pages" / "page_001").mkdir(parents=True, exist_ok=True)
        handoff = {
            "schema_version": 1,
            "kind": "manual_correction_input",
            "source_artifact_root": "/internal/run",
            "source_manifest": "manifest.json",
            "pages": [
                {
                    "page_id": "page_001",
                    "page_number": 1,
                    "source_image": "pages/page_001/source.png",
                    "numbering_final": "pages/page_001/numbering_final.json",
                    "barlines_review": "pages/page_001/barlines_review.json",
                    "correction_output": "corrections",
                }
            ],
        }
        (review_root / "manual_correction_input.json").write_text(
            json.dumps(handoff), encoding="utf-8"
        )
        return handoff

    def fake_final(*, final_root, output_name, **_kwargs):
        final_root = Path(final_root)
        final_root.mkdir(parents=True, exist_ok=True)
        final_pdf = final_root / f"{output_name.replace(' ', '_')}_score_numbered.pdf"
        final_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return {"final_pdf": str(final_pdf), "warnings": ["some labels were omitted"]}

    def build(job_id: str, **kwargs):
        params = {
            "input_root": input_root,
            "artifact_root": artifact_root,
            "base_config_path": config_path,
            "source_commit": "test-commit",
            "job_id_factory": lambda: job_id,
            "pipeline_runner": fake_runner,
            "review_materializer": fake_review,
            "final_materializer": fake_final,
        }
        params.update(kwargs)
        return PipelineJobExecutor(**params)

    return build, artifact_root


def test_executor_publishes_only_contract_artifacts(executor_fixture):
    build, artifact_root = executor_fixture
    events = []
    result = build("job-success")(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.REVIEW,
            config_overrides={"pages": [1], "output_name": "score"},
            caller_reference="caller-1",
        ),
        on_progress=events.append,
    )

    assert result.status is JobStatus.SUCCEEDED
    assert result.pages == {"requested": 1, "processed": 1, "skipped": 0}
    assert result.caller_reference == "caller-1"
    validate_progress_sequence(events)
    assert events[-1].kind is ProgressKind.JOB_SUCCEEDED

    by_id = {artifact.artifact_id: artifact for artifact in result.artifacts}
    assert set(by_id) == {"final.pdf", "review.manual_correction_input"}
    assert result.warnings == (
        {"code": "final_materialization_warning", "message": "some labels were omitted"},
    )
    package = artifact_root / result.job_id
    for artifact in result.artifacts:
        assert (package / artifact.reference).is_file()

    public_result = result.to_json()
    assert "logs/" not in public_result
    assert "pipeline.log" not in public_result
    assert ".engine-work" not in public_result
    assert str(artifact_root) not in public_result

    handoff = json.loads(
        (package / "review" / "manual_correction_input.json").read_text(encoding="utf-8")
    )
    assert handoff["source_job_id"] == result.job_id
    assert "source_artifact_root" not in handoff
    assert "source_manifest" not in handoff

    review_artifact = by_id["review.manual_correction_input"]
    corrections = CorrectionSet(
        correction_set_id="source-check",
        source={
            "source_job_id": result.job_id,
            "source_artifact_id": review_artifact.artifact_id,
            "source_artifact_sha256": review_artifact.sha256,
            "source_contract_version": CONTRACT_VERSION,
            "coordinate_space": dict(review_artifact.coordinate_space or {}),
        },
        records=(),
    )
    corrections.assert_source_matches(
        source_job_id=result.job_id,
        artifact=review_artifact,
    )


def test_execute_payload_maps_missing_fields_to_structured_failure(executor_fixture):
    build, artifact_root = executor_fixture
    events = []
    result = build("job-invalid").execute_payload(
        {
            "schema": "pdfscorebar.engine.job_request.v1",
            "contract_version": CONTRACT_VERSION,
        },
        on_progress=events.append,
    )

    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert result.failure.category is ErrorCategory.INVALID_REQUEST
    assert result.failure.code == "request_invalid"
    assert result.artifacts == ()
    validate_progress_sequence(events)
    assert events[-1].kind is ProgressKind.JOB_FAILED
    assert not (artifact_root / result.job_id / "final").exists()
    assert "debug_context" not in result.to_json()


def test_executor_maps_worker_failure_and_cleans_public_outputs(executor_fixture):
    build, artifact_root = executor_fixture

    def fail_worker(*_args, **_kwargs):
        raise subprocess.CalledProcessError(9, ["synthetic-worker"])

    events = []
    result = build("job-worker", pipeline_runner=fail_worker)(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.FINAL,
            config_overrides={"pages": [1]},
        ),
        on_progress=events.append,
    )

    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "child_process_failed"
    assert result.failure.retryable is True
    assert result.artifacts == ()
    validate_progress_sequence(events)
    assert events[-1].kind is ProgressKind.JOB_FAILED
    package = artifact_root / result.job_id
    assert not (package / "final").exists()
    assert not (package / "review").exists()
    assert not (package / ".engine-work").exists()


def test_executor_reports_correction_source_unavailable(executor_fixture):
    build, _artifact_root = executor_fixture
    source_artifact = {
        "artifact_id": "review.manual_correction_input",
        "role": "review.manual_correction_input",
        "location_kind": "relative_path",
        "reference": "review/manual_correction_input.json",
        "media_type": "application/json",
        "sha256": "a" * 64,
        "coordinate_space": {
            "type": "rendered_page_image",
            "origin": "top_left",
            "units": "pixels",
            "version": "1",
        },
    }
    corrections = CorrectionSet(
        correction_set_id="c1",
        source={
            "source_job_id": "source-job",
            "source_artifact_id": source_artifact["artifact_id"],
            "source_artifact_sha256": source_artifact["sha256"],
            "source_contract_version": CONTRACT_VERSION,
            "coordinate_space": source_artifact["coordinate_space"],
        },
        records=(),
    )

    result = build("job-correction")(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.REVIEW,
            config_overrides={},
            corrections=corrections,
        )
    )

    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert result.failure.category is ErrorCategory.CORRECTION
    assert result.failure.code in {"correction_execution_unavailable", "correction_source_invalid"}


def test_executor_sanitized_output_name_uses_materialized_path(executor_fixture):
    build, artifact_root = executor_fixture
    result = build("job-sanitized")(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.FINAL,
            config_overrides={"pages": [1], "output_name": "my score"},
        )
    )
    assert result.status is JobStatus.SUCCEEDED
    final = next(item for item in result.artifacts if item.artifact_id == "final.pdf")
    assert final.reference == "final/my_score_score_numbered.pdf"
    assert (artifact_root / result.job_id / final.reference).is_file()
    assert not (artifact_root / result.job_id / ".engine-work").exists()


def test_debug_telemetry_contains_completed_materialization_stage(executor_fixture):
    build, artifact_root = executor_fixture
    result = build("job-debug")(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.DEBUG,
            config_overrides={"pages": [1]},
        )
    )
    assert result.status is JobStatus.SUCCEEDED
    artifact = next(item for item in result.artifacts if item.artifact_id == "debug.telemetry")
    payload = json.loads((artifact_root / result.job_id / artifact.reference).read_text())
    assert any(
        item.get("stage_id") == "artifact_materialization" and item.get("state") == "completed"
        for item in payload.get("stage_spans", [])
    )


def test_executor_monitors_attempt_disk_budget_and_cleans_work(executor_fixture, monkeypatch):
    build, artifact_root = executor_fixture
    monitor_checked = threading.Event()
    original_check = engine_executor_module._check_attempt_budget

    def tracked_check(root, policy):
        if threading.current_thread().name == "engine-disk-budget":
            monitor_checked.set()
        return original_check(root, policy)

    monkeypatch.setattr(engine_executor_module, "_check_attempt_budget", tracked_check)

    def oversized_runner(_config_path, *, run_id, output_root, **_kwargs):
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "oversized.bin").write_bytes(b"x" * 2048)
        assert monitor_checked.wait(timeout=2)
        time.sleep(0.3)
        return run_dir

    result = build(
        "job-over-budget",
        pipeline_runner=oversized_runner,
        safety_policy=JobSafetyPolicy(max_attempt_disk_bytes=1024),
    )(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.FINAL,
            config_overrides={"pages": [1]},
        )
    )
    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "attempt_disk_budget_exceeded"
    assert not (artifact_root / result.job_id / ".engine-work").exists()


def test_retention_failure_emits_only_failed_terminal(executor_fixture, monkeypatch):
    build, artifact_root = executor_fixture
    original_replace = Path.replace

    def fail_retention(source, target):
        if source.name == ".engine-work" and Path(target).name == ".engine-retained":
            raise OSError("synthetic retention failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_retention)
    events = []
    result = build("job-retention-failure")(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.REVIEW,
            config_overrides={"pages": [1]},
        ),
        on_progress=events.append,
    )
    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert [event for event in events if event.terminal][-1].kind is ProgressKind.JOB_FAILED
    assert sum(event.terminal for event in events) == 1
    package = artifact_root / result.job_id
    assert not (package / "final").exists()
    assert not (package / "review").exists()
    assert not (package / ".engine-work").exists()
    assert not (package / ".engine-retained").exists()
