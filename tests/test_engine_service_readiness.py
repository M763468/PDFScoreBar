from __future__ import annotations

import json
import subprocess
from pathlib import Path

import fitz
import pytest

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
        final_pdf = final_root / f"{output_name}_score_numbered.pdf"
        final_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return {"final_pdf": str(final_pdf)}

    def build(job_id: str, **kwargs):
        return PipelineJobExecutor(
            input_root=input_root,
            artifact_root=artifact_root,
            base_config_path=config_path,
            source_commit="test-commit",
            job_id_factory=lambda: job_id,
            pipeline_runner=fake_runner,
            review_materializer=fake_review,
            final_materializer=fake_final,
            **kwargs,
        )

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


def test_executor_reports_unconnected_correction_execution(executor_fixture):
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
    assert result.failure.code == "correction_execution_unavailable"
