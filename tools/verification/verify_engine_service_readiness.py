#!/usr/bin/env python3
"""Exercise the service-facing one-job boundary without accuracy assertions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from src.pipeline.engine_contract import (
    CONTRACT_VERSION,
    SCHEMA_REQUEST,
    CorrectionSet,
    JobRequest,
    JobStatus,
    OutputProfile,
    validate_progress_sequence,
)
from src.pipeline.engine_executor import PipelineJobExecutor
from src.pipeline.engine_input_safety import DEFAULT_JOB_SAFETY_POLICY


def _prepare_fixture(repo_root: Path) -> tuple[Path, Path]:
    fixture_root = repo_root / "artifacts" / "service_readiness_fixture"
    jobs_root = repo_root / "artifacts" / "service_readiness_jobs"
    shutil.rmtree(fixture_root, ignore_errors=True)
    shutil.rmtree(jobs_root, ignore_errors=True)
    fixture_root.mkdir(parents=True, exist_ok=True)

    pdf_path = fixture_root / "service_score.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    for y in (150, 155, 160, 165, 170):
        page.draw_line((40, y), (260, y), width=0.8)
    for x in (60, 120, 180, 240):
        page.draw_line((x, 148), (x, 172), width=1.2)
    document.save(pdf_path)
    document.close()

    mask = Image.new("L", (600, 800), 0)
    draw = ImageDraw.Draw(mask)
    for y in (300, 310, 320, 330, 340):
        draw.line((80, y, 520, y), fill=255, width=2)
    mask.save(fixture_root / "page_001_staff_mask.png")

    barlines = [[118, 294, 122, 346], [238, 294, 242, 346], [358, 294, 362, 346], [478, 294, 482, 346]]
    (fixture_root / "page_001_barlines.json").write_text(
        json.dumps(barlines) + "\n", encoding="utf-8"
    )
    return pdf_path, jobs_root


def _executor(
    repo_root: Path,
    jobs_root: Path,
    job_id: str,
    **kwargs,
) -> PipelineJobExecutor:
    return PipelineJobExecutor(
        input_root=repo_root,
        artifact_root=jobs_root,
        base_config_path=repo_root / "configs" / "service_readiness_smoke.yaml",
        source_commit=os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT") or "service-smoke",
        job_id_factory=lambda: job_id,
        **kwargs,
    )


def _assert_failure(result, events, jobs_root: Path, code: str) -> None:
    assert result.status is JobStatus.FAILED, result.to_json(include_debug_context=True)
    assert result.failure is not None
    assert result.failure.code == code, result.to_json(include_debug_context=True)
    assert result.artifacts == ()
    validate_progress_sequence(events)
    assert events[-1].terminal
    package = jobs_root / result.job_id
    assert not (package / "final").exists()
    assert not (package / "review").exists()


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    os.chdir(repo_root)
    pdf_path, jobs_root = _prepare_fixture(repo_root)
    reference = pdf_path.relative_to(repo_root).as_posix()

    success_events = []
    request = JobRequest(
        input={"kind": "local_path", "reference": reference},
        output_profile=OutputProfile.REVIEW,
        config_overrides={"pages": [1], "output_name": "service_smoke"},
        caller_reference="service-readiness-smoke",
    )
    success = _executor(repo_root, jobs_root, "service-success")(
        request, on_progress=success_events.append
    )
    assert success.status is JobStatus.SUCCEEDED, success.to_json(include_debug_context=True)
    validate_progress_sequence(success_events)
    assert success_events[-1].terminal
    assert success.pages == {"requested": 1, "processed": 1, "skipped": 0}

    by_id = {artifact.artifact_id: artifact for artifact in success.artifacts}
    assert set(by_id) == {"final.pdf", "review.manual_correction_input"}
    package = jobs_root / success.job_id
    for artifact in success.artifacts:
        assert artifact.location_kind == "relative_path"
        assert (package / artifact.reference).is_file()

    public_json = success.to_json()
    for forbidden in ("logs/", "pipeline.log", ".engine-work", str(repo_root)):
        assert forbidden not in public_json

    handoff_artifact = by_id["review.manual_correction_input"]
    handoff_path = package / handoff_artifact.reference
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["source_job_id"] == success.job_id
    assert "source_artifact_root" not in handoff
    assert "source_manifest" not in handoff

    corrections = CorrectionSet(
        correction_set_id="service-smoke-source-check",
        source={
            "source_job_id": success.job_id,
            "source_artifact_id": handoff_artifact.artifact_id,
            "source_artifact_sha256": handoff_artifact.sha256,
            "source_contract_version": CONTRACT_VERSION,
            "coordinate_space": dict(handoff_artifact.coordinate_space or {}),
        },
        records=(),
    )
    corrections.assert_source_matches(
        source_job_id=success.job_id,
        artifact=handoff_artifact,
    )

    corrupt = pdf_path.with_name("corrupt.pdf")
    corrupt.write_bytes(b"not-a-pdf")
    corrupt_events = []
    corrupt_result = _executor(repo_root, jobs_root, "service-corrupt")(
        JobRequest(
            input={
                "kind": "local_path",
                "reference": corrupt.relative_to(repo_root).as_posix(),
            },
            output_profile=OutputProfile.FINAL,
            config_overrides={},
        ),
        on_progress=corrupt_events.append,
    )
    _assert_failure(
        corrupt_result,
        corrupt_events,
        jobs_root,
        "input_pdf_invalid",
    )

    limit_events = []
    limit_result = _executor(
        repo_root,
        jobs_root,
        "service-limit",
        safety_policy=replace(DEFAULT_JOB_SAFETY_POLICY, max_pdf_bytes=1),
    )(
        JobRequest(
            input={"kind": "local_path", "reference": reference},
            output_profile=OutputProfile.FINAL,
            config_overrides={},
        ),
        on_progress=limit_events.append,
    )
    _assert_failure(
        limit_result,
        limit_events,
        jobs_root,
        "input_pdf_bytes_limit_exceeded",
    )

    malformed_events = []
    malformed_result = _executor(repo_root, jobs_root, "service-malformed").execute_payload(
        {
            "schema": SCHEMA_REQUEST,
            "contract_version": CONTRACT_VERSION,
        },
        on_progress=malformed_events.append,
    )
    _assert_failure(
        malformed_result,
        malformed_events,
        jobs_root,
        "request_invalid",
    )

    def fail_worker(*_args, **_kwargs):
        raise subprocess.CalledProcessError(7, ["synthetic-service-worker"])

    worker_events = []
    worker_result = _executor(
        repo_root,
        jobs_root,
        "service-worker-failure",
        pipeline_runner=fail_worker,
    )(
        JobRequest(
            input={"kind": "local_path", "reference": reference},
            output_profile=OutputProfile.FINAL,
            config_overrides={"pages": [1]},
        ),
        on_progress=worker_events.append,
    )
    _assert_failure(
        worker_result,
        worker_events,
        jobs_root,
        "child_process_failed",
    )

    print(
        json.dumps(
            {
                "status": "passed",
                "job_id": success.job_id,
                "artifacts": [artifact.reference for artifact in success.artifacts],
                "progress_events": len(success_events),
                "failure_codes": [
                    corrupt_result.failure.code,
                    limit_result.failure.code,
                    malformed_result.failure.code,
                    worker_result.failure.code,
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
