import math

import pytest

from src.pipeline.engine_contract import (
    ArtifactDescriptor,
    ContractValidationError,
    CorrectionSet,
    EngineError,
    ErrorCategory,
    JobRequest,
    JobResult,
    JobStatus,
    ProgressEvent,
    ProgressKind,
    canonical_json,
    validate_progress_sequence,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
COORDINATE_SPACE = {
    "type": "rendered_page_image",
    "origin": "top_left",
    "units": "pixels",
    "version": "1",
}


def _review_artifact(
    sha256: str = SHA_A,
) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_id="review.manual_correction_input",
        role="review.manual_correction_input",
        location_kind="relative_path",
        reference="review/manual_correction_input.json",
        media_type="application/json",
        sha256=sha256,
        coordinate_space=COORDINATE_SPACE,
    )


def _provenance() -> dict[str, str]:
    return {
        "engine_version": "0.1.0",
        "pipeline_version": "dense-v1",
        "source_commit": "abc123",
    }


def test_job_request_round_trip_is_deterministic_and_forward_compatible():
    payload = {
        "schema": "pdfscorebar.engine.job_request.v1",
        "contract_version": "1",
        "input": {
            "kind": "local_path",
            "reference": "score.pdf",
            "sha256": SHA_A,
        },
        "output_profile": "review",
        "config_overrides": {
            "pages": [3, 1, 3],
            "output_name": "score",
        },
        "caller_reference": "cli-42",
        "future_optional_field": {"ignored": True},
    }

    request = JobRequest.from_dict(payload)

    assert request.config_overrides["pages"] == [1, 3]
    assert JobRequest.from_json(request.to_json()) == request
    assert request.to_json() == canonical_json(request.to_dict())
    assert "logs/" not in request.to_json()


def test_unknown_contract_version_is_rejected():
    payload = {
        "schema": "pdfscorebar.engine.job_request.v1",
        "contract_version": "2",
        "input": {
            "kind": "local_path",
            "reference": "score.pdf",
        },
    }

    with pytest.raises(ContractValidationError):
        JobRequest.from_dict(payload)


def test_corrections_map_current_operations_and_reject_stale_source():
    artifact = _review_artifact()
    correction_set = CorrectionSet(
        correction_set_id="correction-set-1",
        source={
            "source_job_id": "job-1",
            "source_artifact_id": artifact.artifact_id,
            "source_artifact_sha256": SHA_A,
            "source_contract_version": "1",
            "coordinate_space": COORDINATE_SPACE,
        },
        records=(
            {
                "correction_id": "z",
                "operation": "barline.remove",
                "target": {
                    "page": 0,
                    "bbox": [1, 2, 3, 4],
                },
            },
            {
                "correction_id": "a",
                "operation": "mmr.set_measure_span",
                "target": {
                    "page": 0,
                    "system": 1,
                    "measure": 2,
                },
                "value": {"measure_span": 4},
            },
            {
                "correction_id": "m",
                "operation": "movement_boundary.set_decision",
                "target": {
                    "page": 0,
                    "system": 2,
                },
                "value": {"decision": "no_boundary"},
            },
        ),
    )

    records = correction_set.to_dict()["records"]
    assert [record["correction_id"] for record in records] == [
        "a",
        "m",
        "z",
    ]

    correction_set.assert_source_matches(
        source_job_id="job-1",
        artifact=artifact,
    )

    with pytest.raises(
        ContractValidationError,
        match="stale correction source",
    ):
        correction_set.assert_source_matches(
            source_job_id="job-1",
            artifact=_review_artifact(SHA_B),
        )


def test_duplicate_correction_ids_and_internal_override_are_rejected():
    source = {
        "source_job_id": "job-1",
        "source_artifact_id": "artifact-1",
        "source_artifact_sha256": SHA_A,
        "source_contract_version": "1",
        "coordinate_space": COORDINATE_SPACE,
    }
    record = {
        "correction_id": "same",
        "operation": "mmr.suppress",
        "target": {
            "page": 0,
            "system": 0,
            "measure": 0,
        },
    }

    with pytest.raises(
        ContractValidationError,
        match="duplicate",
    ):
        CorrectionSet("set", source, (record, record))

    with pytest.raises(
        ContractValidationError,
        match="unsupported public config override",
    ):
        JobRequest(
            input={
                "kind": "local_path",
                "reference": "score.pdf",
            },
            config_overrides={
                "run.output_root": "logs/x",
            },
        )


def test_malformed_corrections_and_failure_payloads_are_rejected():
    request_payload = {
        "schema": "pdfscorebar.engine.job_request.v1",
        "contract_version": "1",
        "input": {
            "kind": "local_path",
            "reference": "score.pdf",
        },
        "output_profile": "final",
        "config_overrides": {},
        "corrections": [],
    }
    with pytest.raises(
        ContractValidationError,
        match="corrections must be an object",
    ):
        JobRequest.from_dict(request_payload)

    result_payload = {
        "schema": "pdfscorebar.engine.job_result.v1",
        "contract_version": "1",
        "job_id": "job",
        "status": "succeeded",
        "provenance": _provenance(),
        "pages": {
            "requested": 1,
            "processed": 1,
            "skipped": 0,
        },
        "artifacts": [],
        "warnings": [],
        "review": {
            "required": False,
            "reason_codes": [],
        },
        "failure": [],
    }
    with pytest.raises(
        ContractValidationError,
        match="failure must be an object",
    ):
        JobResult.from_dict(result_payload)

    malformed_artifact_payload = {
        "schema": "pdfscorebar.engine.job_result.v1",
        "contract_version": "1",
        "job_id": "job",
        "status": "succeeded",
        "provenance": _provenance(),
        "pages": {
            "requested": 1,
            "processed": 1,
            "skipped": 0,
        },
        "artifacts": [None],
        "warnings": [],
        "review": {
            "required": False,
            "reason_codes": [],
        },
    }
    with pytest.raises(
        ContractValidationError,
        match="artifact entries must be objects",
    ):
        JobResult.from_dict(malformed_artifact_payload)


def test_success_warning_review_required_and_failure_results():
    final = ArtifactDescriptor(
        artifact_id="final.pdf",
        role="final.score_numbered_pdf",
        location_kind="relative_path",
        reference="final/score_score_numbered.pdf",
        media_type="application/pdf",
        sha256=SHA_B,
    )
    success = JobResult(
        job_id="job-success",
        status=JobStatus.SUCCEEDED,
        provenance=_provenance(),
        pages={
            "requested": 2,
            "processed": 2,
            "skipped": 0,
        },
        artifacts=(final,),
        resources={"wall_time_seconds": 4.2},
    )

    assert JobResult.from_json(success.to_json()) == success

    warning = JobResult(
        job_id="job-warning",
        status="succeeded",
        provenance=_provenance(),
        pages={
            "requested": 2,
            "processed": 1,
            "skipped": 1,
        },
        artifacts=(final,),
        warnings=(
            {
                "code": "page_skipped",
                "message": "One page was skipped.",
            },
        ),
    )
    assert warning.to_dict()["warnings"][0]["code"] == "page_skipped"

    review = JobResult(
        job_id="job-review",
        status="review_required",
        provenance=_provenance(),
        pages={
            "requested": 1,
            "processed": 1,
            "skipped": 0,
        },
        artifacts=(_review_artifact(),),
        review={
            "required": True,
            "reason_codes": [
                "movement_boundary_ambiguous",
            ],
            "correction_source_artifact_id": ("review.manual_correction_input"),
        },
    )
    assert review.to_dict()["review"]["required"] is True

    failure = JobResult(
        job_id="job-failure",
        status="failed",
        provenance=_provenance(),
        pages={
            "requested": 1,
            "processed": 0,
            "skipped": 0,
        },
        failure=EngineError(
            category=ErrorCategory.INPUT,
            code="input_pdf_invalid",
            public_message=("The input PDF could not be read."),
            user_actionable=True,
            retryable=False,
            debug_context={
                "path": "/internal/score.pdf",
            },
        ),
    )

    assert "debug_context" not in failure.to_dict()["failure"]
    assert "debug_context" in failure.to_dict(include_debug_context=True)["failure"]


def test_invalid_result_shapes_are_rejected():
    with pytest.raises(
        ContractValidationError,
        match="requires failure",
    ):
        JobResult(
            job_id="job",
            status="failed",
            provenance=_provenance(),
            pages={
                "requested": 1,
                "processed": 0,
                "skipped": 0,
            },
        )

    with pytest.raises(
        ContractValidationError,
        match="review.required",
    ):
        JobResult(
            job_id="job",
            status="review_required",
            provenance=_provenance(),
            pages={
                "requested": 1,
                "processed": 1,
                "skipped": 0,
            },
        )

    with pytest.raises(
        ContractValidationError,
        match="correction_source_artifact_id",
    ):
        JobResult(
            job_id="job",
            status="review_required",
            provenance=_provenance(),
            pages={
                "requested": 1,
                "processed": 1,
                "skipped": 0,
            },
            review={
                "required": True,
                "reason_codes": ["movement_boundary_ambiguous"],
            },
        )

    malformed_review_source_payload = {
        "schema": "pdfscorebar.engine.job_result.v1",
        "contract_version": "1",
        "job_id": "job",
        "status": "review_required",
        "provenance": _provenance(),
        "pages": {
            "requested": 1,
            "processed": 1,
            "skipped": 0,
        },
        "artifacts": [_review_artifact().to_dict()],
        "warnings": [],
        "review": {
            "required": True,
            "reason_codes": ["movement_boundary_ambiguous"],
            "correction_source_artifact_id": [],
        },
    }
    with pytest.raises(
        ContractValidationError,
        match="review.correction_source_artifact_id must be a non-empty string",
    ):
        JobResult.from_dict(malformed_review_source_payload)

    missing_review_payload = {
        "schema": "pdfscorebar.engine.job_result.v1",
        "contract_version": "1",
        "job_id": "job",
        "status": "succeeded",
        "provenance": _provenance(),
        "pages": {
            "requested": 1,
            "processed": 1,
            "skipped": 0,
        },
        "artifacts": [],
        "warnings": [],
    }
    with pytest.raises(
        ContractValidationError,
        match=r"job result missing required field\(s\): review",
    ):
        JobResult.from_dict(missing_review_payload)

    source_without_hash = ArtifactDescriptor(
        artifact_id="review.manual_correction_input",
        role="review.manual_correction_input",
        location_kind="relative_path",
        reference="review/manual_correction_input.json",
        media_type="application/json",
        coordinate_space=COORDINATE_SPACE,
    )
    with pytest.raises(
        ContractValidationError,
        match="correction source artifact requires sha256",
    ):
        JobResult(
            job_id="job",
            status="review_required",
            provenance=_provenance(),
            pages={
                "requested": 1,
                "processed": 1,
                "skipped": 0,
            },
            artifacts=(source_without_hash,),
            review={
                "required": True,
                "reason_codes": ["movement_boundary_ambiguous"],
                "correction_source_artifact_id": source_without_hash.artifact_id,
            },
        )

    source_without_coordinate_space = ArtifactDescriptor(
        artifact_id="review.manual_correction_input",
        role="review.manual_correction_input",
        location_kind="relative_path",
        reference="review/manual_correction_input.json",
        media_type="application/json",
        sha256=SHA_A,
    )
    with pytest.raises(
        ContractValidationError,
        match="correction source artifact requires coordinate_space",
    ):
        JobResult(
            job_id="job",
            status="review_required",
            provenance=_provenance(),
            pages={
                "requested": 1,
                "processed": 1,
                "skipped": 0,
            },
            artifacts=(source_without_coordinate_space,),
            review={
                "required": True,
                "reason_codes": ["movement_boundary_ambiguous"],
                "correction_source_artifact_id": source_without_coordinate_space.artifact_id,
            },
        )


def test_required_wire_fields_and_malformed_scalar_types_are_rejected():
    request_payload = {
        "schema": "pdfscorebar.engine.job_request.v1",
        "contract_version": "1",
        "input": {
            "kind": "local_path",
            "reference": "score.pdf",
        },
        "output_profile": "final",
        "config_overrides": {},
    }
    for missing in ("output_profile", "config_overrides"):
        malformed = dict(request_payload)
        del malformed[missing]
        with pytest.raises(
            ContractValidationError,
            match="job request missing required field",
        ):
            JobRequest.from_dict(malformed)

    malformed_config = dict(request_payload)
    malformed_config["config_overrides"] = None
    with pytest.raises(
        ContractValidationError,
        match="config_overrides must be an object",
    ):
        JobRequest.from_dict(malformed_config)

    malformed_kind = {
        **request_payload,
        "input": {
            "kind": [],
            "reference": "score.pdf",
        },
    }
    with pytest.raises(
        ContractValidationError,
        match="input.kind must be a non-empty string",
    ):
        JobRequest.from_dict(malformed_kind)

    correction_set = CorrectionSet(
        correction_set_id="set-1",
        source={
            "source_job_id": "job-1",
            "source_artifact_id": "review.manual_correction_input",
            "source_artifact_sha256": SHA_A,
            "source_contract_version": "1",
            "coordinate_space": COORDINATE_SPACE,
        },
        records=(),
    )
    serialized_corrections = correction_set.to_dict()
    for missing in ("records", "reprocess_mode", "conflict_policy"):
        malformed = dict(serialized_corrections)
        del malformed[missing]
        with pytest.raises(
            ContractValidationError,
            match="correction set missing required field",
        ):
            CorrectionSet.from_dict(malformed)

    with pytest.raises(
        ContractValidationError,
        match="coordinate_space missing required field",
    ):
        ArtifactDescriptor(
            artifact_id="review.manual_correction_input",
            role="review.manual_correction_input",
            location_kind="relative_path",
            reference="review/manual_correction_input.json",
            media_type="application/json",
            sha256=SHA_A,
            coordinate_space={},
        )

    terminal_event = ProgressEvent(
        "job-1",
        0,
        ProgressKind.JOB_SUCCEEDED,
        "job",
    ).to_dict()
    terminal_event["terminal"] = 1
    with pytest.raises(
        ContractValidationError,
        match="progress.terminal must be boolean",
    ):
        ProgressEvent.from_dict(terminal_event)

    malformed_stage = ProgressEvent(
        "job-1",
        0,
        ProgressKind.JOB_STARTED,
        "job",
    ).to_dict()
    malformed_stage["stage_id"] = []
    with pytest.raises(
        ContractValidationError,
        match="progress.stage_id must be a non-empty string",
    ):
        ProgressEvent.from_dict(malformed_stage)


def test_progress_sequence_is_monotonic_and_terminal():
    events = [
        ProgressEvent(
            "job-1",
            0,
            ProgressKind.JOB_STARTED,
            "job",
        ),
        ProgressEvent(
            "job-1",
            1,
            ProgressKind.STAGE_PROGRESS,
            "score_detection",
            page_number=1,
            completed_units=1,
            total_units=2,
            unit="page",
        ),
        ProgressEvent(
            "job-1",
            2,
            ProgressKind.JOB_SUCCEEDED,
            "job",
        ),
    ]

    validate_progress_sequence(events)
    assert events[-1].to_dict()["terminal"] is True

    with pytest.raises(
        ContractValidationError,
        match="after terminal",
    ):
        validate_progress_sequence(
            events
            + [
                ProgressEvent(
                    "job-1",
                    3,
                    ProgressKind.STAGE_COMPLETED,
                    "score_detection",
                )
            ]
        )


def test_artifact_relative_path_cannot_escape_package():
    with pytest.raises(
        ContractValidationError,
        match="inside its package",
    ):
        ArtifactDescriptor(
            artifact_id="x",
            role="review.debug",
            location_kind="relative_path",
            reference="../logs/internal.json",
            media_type="application/json",
        )


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
