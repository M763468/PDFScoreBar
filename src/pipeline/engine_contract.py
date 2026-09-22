"""Versioned one-job engine contract for external PDFScoreBar callers."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Protocol

CONTRACT_VERSION = "1"
SCHEMA_REQUEST = "pdfscorebar.engine.job_request.v1"
SCHEMA_RESULT = "pdfscorebar.engine.job_result.v1"
SCHEMA_PROGRESS = "pdfscorebar.engine.progress_event.v1"
SCHEMA_ERROR = "pdfscorebar.engine.error.v1"
SCHEMA_CORRECTIONS = "pdfscorebar.engine.correction_set.v1"

STAGE_IDS = frozenset(
    {
        "job",
        "input_validation",
        "pdf_render",
        "score_detection",
        "measure_construction",
        "measure_number_recognition",
        "correction_application",
        "numbering",
        "artifact_materialization",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContractValidationError(ValueError):
    """Raised when a serialized value violates the v1 public contract."""


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class OutputProfile(_StringEnum):
    FINAL = "final"
    REVIEW = "review"
    DEBUG = "debug"


class JobStatus(_StringEnum):
    SUCCEEDED = "succeeded"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(_StringEnum):
    INVALID_REQUEST = "invalid_request"
    INPUT = "input"
    CORRECTION = "correction"
    RESOURCE = "resource"
    DEPENDENCY = "dependency"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class ProgressKind(_StringEnum):
    JOB_STARTED = "job_started"
    STAGE_STARTED = "stage_started"
    STAGE_PROGRESS = "stage_progress"
    STAGE_COMPLETED = "stage_completed"
    JOB_SUCCEEDED = "job_succeeded"
    JOB_REVIEW_REQUIRED = "job_review_required"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"


class CorrectionOperation(_StringEnum):
    MMR_SET_MEASURE_SPAN = "mmr.set_measure_span"
    MMR_SUPPRESS = "mmr.suppress"
    MEASURE_FORCE = "measure.force_measure"
    BARLINE_ADD = "barline.add"
    BARLINE_REMOVE = "barline.remove"
    MOVEMENT_BOUNDARY_SET_DECISION = "movement_boundary.set_decision"


_TERMINAL_PROGRESS = {
    ProgressKind.JOB_SUCCEEDED,
    ProgressKind.JOB_REVIEW_REQUIRED,
    ProgressKind.JOB_FAILED,
    ProgressKind.JOB_CANCELLED,
}


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")
    return value


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be an object")
    return {str(key): item for key, item in value.items()}


def _sha256(value: Any, field_name: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    value = _require_string(value, field_name).lower()
    if not _SHA256.fullmatch(value):
        raise ContractValidationError(f"{field_name} must be a SHA-256 hex digest")
    return value


def _enum(
    enum_type: type[_StringEnum],
    value: Any,
    field_name: str,
) -> _StringEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(
            f"unsupported {field_name}: {value!r}"
        ) from exc


def _envelope(payload: Mapping[str, Any], schema: str) -> None:
    if (
        payload.get("schema") != schema
        or payload.get("contract_version") != CONTRACT_VERSION
    ):
        raise ContractValidationError(f"unsupported schema/version for {schema}")


def _nonnegative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContractValidationError(f"{field_name} must be an integer >= 0")
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ContractValidationError(f"{field_name} must be an integer >= 1")
    return value


def canonical_json(value: Any) -> str:
    """Serialize a contract value deterministically and reject NaN/Infinity."""

    if hasattr(value, "to_dict"):
        value = value.to_dict()
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class ArtifactDescriptor:
    artifact_id: str
    role: str
    location_kind: str
    reference: str
    media_type: str
    sha256: str | None = None
    coordinate_space: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_string(self.artifact_id, "artifact_id")
        _require_string(self.role, "artifact.role")
        if self.location_kind not in {"relative_path", "engine_ref"}:
            raise ContractValidationError(
                "artifact.location_kind must be relative_path or engine_ref"
            )
        _require_string(self.reference, "artifact.reference")
        _require_string(self.media_type, "artifact.media_type")
        object.__setattr__(
            self,
            "sha256",
            _sha256(self.sha256, "artifact.sha256"),
        )
        if self.coordinate_space is not None:
            object.__setattr__(
                self,
                "coordinate_space",
                _object(self.coordinate_space, "coordinate_space"),
            )
        if self.location_kind == "relative_path":
            path = PurePosixPath(self.reference)
            if path.is_absolute() or ".." in path.parts:
                raise ContractValidationError(
                    "artifact relative_path must stay inside its package"
                )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "role": self.role,
            "location_kind": self.location_kind,
            "reference": self.reference,
            "media_type": self.media_type,
        }
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        if self.coordinate_space is not None:
            result["coordinate_space"] = dict(self.coordinate_space)
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactDescriptor":
        return cls(
            artifact_id=payload.get("artifact_id"),
            role=payload.get("role"),
            location_kind=payload.get("location_kind"),
            reference=payload.get("reference"),
            media_type=payload.get("media_type"),
            sha256=payload.get("sha256"),
            coordinate_space=payload.get("coordinate_space"),
        )


def _validate_correction_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _object(record, "correction record")
    correction_id = _require_string(
        normalized.get("correction_id"),
        "correction_id",
    )
    operation = _enum(
        CorrectionOperation,
        normalized.get("operation"),
        "correction.operation",
    )
    target = _object(normalized.get("target"), "correction.target")
    value = _object(normalized.get("value"), "correction.value")
    _nonnegative_int(target.get("page"), "correction.target.page")

    measure_operations = {
        CorrectionOperation.MMR_SET_MEASURE_SPAN,
        CorrectionOperation.MMR_SUPPRESS,
        CorrectionOperation.MEASURE_FORCE,
    }
    if operation in measure_operations:
        _nonnegative_int(
            target.get("system"),
            "correction.target.system",
        )
        _nonnegative_int(
            target.get("measure"),
            "correction.target.measure",
        )

    if operation is CorrectionOperation.MMR_SET_MEASURE_SPAN:
        _positive_int(
            value.get("measure_span"),
            "correction.value.measure_span",
        )

    if operation in {
        CorrectionOperation.BARLINE_ADD,
        CorrectionOperation.BARLINE_REMOVE,
    }:
        bbox = target.get("bbox")
        valid_bbox = (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(
                not isinstance(item, bool)
                and isinstance(item, (int, float))
                and math.isfinite(float(item))
                for item in bbox
            )
        )
        if not valid_bbox:
            raise ContractValidationError(
                "barline correction target.bbox must contain four finite numbers"
            )

    if operation is CorrectionOperation.MOVEMENT_BOUNDARY_SET_DECISION:
        _nonnegative_int(
            target.get("system"),
            "correction.target.system",
        )
        if value.get("decision") not in {"boundary", "no_boundary"}:
            raise ContractValidationError(
                "movement boundary decision must be boundary or no_boundary"
            )

    result: dict[str, Any] = {
        "correction_id": correction_id,
        "operation": operation.value,
        "target": target,
    }
    if value:
        result["value"] = value
    if normalized.get("reason") is not None:
        result["reason"] = _require_string(
            normalized["reason"],
            "correction.reason",
        )
    return result


@dataclass(frozen=True)
class CorrectionSet:
    correction_set_id: str
    source: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...]
    schema: str = SCHEMA_CORRECTIONS
    contract_version: str = CONTRACT_VERSION
    reprocess_mode: str = "reuse_compatible_artifacts"
    conflict_policy: str = "reject"

    def __post_init__(self) -> None:
        _require_string(self.correction_set_id, "correction_set_id")
        if (
            self.schema != SCHEMA_CORRECTIONS
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ContractValidationError(
                "unsupported correction set schema/version"
            )
        if (
            self.reprocess_mode != "reuse_compatible_artifacts"
            or self.conflict_policy != "reject"
        ):
            raise ContractValidationError(
                "v1 corrections must reuse compatible artifacts and reject conflicts"
            )

        source = _object(self.source, "correction.source")
        for key in (
            "source_job_id",
            "source_artifact_id",
            "source_contract_version",
        ):
            _require_string(
                source.get(key),
                f"correction.source.{key}",
            )
        source["source_artifact_sha256"] = _sha256(
            source.get("source_artifact_sha256"),
            "correction.source.source_artifact_sha256",
            required=True,
        )
        source["coordinate_space"] = _object(
            source.get("coordinate_space"),
            "correction.source.coordinate_space",
        )

        records = tuple(
            _validate_correction_record(record)
            for record in self.records
        )
        ids = [record["correction_id"] for record in records]
        if len(ids) != len(set(ids)):
            raise ContractValidationError(
                "duplicate correction_id values are not allowed"
            )
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "records", records)

    def assert_source_matches(
        self,
        *,
        source_job_id: str,
        artifact: ArtifactDescriptor,
        contract_version: str = CONTRACT_VERSION,
    ) -> None:
        pairs = {
            "source_job_id": (
                self.source["source_job_id"],
                source_job_id,
            ),
            "source_artifact_id": (
                self.source["source_artifact_id"],
                artifact.artifact_id,
            ),
            "source_artifact_sha256": (
                self.source["source_artifact_sha256"],
                artifact.sha256,
            ),
            "source_contract_version": (
                self.source["source_contract_version"],
                contract_version,
            ),
            "coordinate_space": (
                self.source["coordinate_space"],
                artifact.coordinate_space,
            ),
        }
        for field_name, (expected, actual) in pairs.items():
            if expected != actual:
                raise ContractValidationError(
                    f"stale correction source: {field_name} mismatch"
                )

    def to_dict(self) -> dict[str, Any]:
        records = sorted(
            (dict(record) for record in self.records),
            key=lambda record: record["correction_id"],
        )
        return {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "correction_set_id": self.correction_set_id,
            "source": dict(self.source),
            "reprocess_mode": self.reprocess_mode,
            "conflict_policy": self.conflict_policy,
            "records": records,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CorrectionSet":
        _envelope(payload, SCHEMA_CORRECTIONS)
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise ContractValidationError(
                "correction records must be a list"
            )
        return cls(
            correction_set_id=payload.get("correction_set_id"),
            source=_object(
                payload.get("source"),
                "correction.source",
            ),
            records=tuple(records),
            schema=payload["schema"],
            contract_version=payload["contract_version"],
            reprocess_mode=payload.get(
                "reprocess_mode",
                "reuse_compatible_artifacts",
            ),
            conflict_policy=payload.get(
                "conflict_policy",
                "reject",
            ),
        )


@dataclass(frozen=True)
class JobRequest:
    input: Mapping[str, Any]
    output_profile: OutputProfile = OutputProfile.FINAL
    config_overrides: Mapping[str, Any] = field(default_factory=dict)
    corrections: CorrectionSet | None = None
    caller_reference: str | None = None
    schema: str = SCHEMA_REQUEST
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema != SCHEMA_REQUEST
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ContractValidationError(
                "unsupported job request schema/version"
            )

        input_ref = _object(self.input, "input")
        if input_ref.get("kind") not in {"local_path", "engine_ref"}:
            raise ContractValidationError(
                "input.kind must be local_path or engine_ref"
            )
        _require_string(
            input_ref.get("reference"),
            "input.reference",
        )
        if input_ref.get("sha256") is not None:
            input_ref["sha256"] = _sha256(
                input_ref["sha256"],
                "input.sha256",
            )
        object.__setattr__(self, "input", input_ref)
        object.__setattr__(
            self,
            "output_profile",
            _enum(
                OutputProfile,
                self.output_profile,
                "output_profile",
            ),
        )

        overrides = _object(
            self.config_overrides,
            "config_overrides",
        )
        unknown = set(overrides) - {"pages", "output_name"}
        if unknown:
            raise ContractValidationError(
                "unsupported public config override(s): "
                f"{sorted(unknown)}"
            )
        if "pages" in overrides:
            pages = overrides["pages"]
            if not isinstance(pages, list) or not pages:
                raise ContractValidationError(
                    "config_overrides.pages must be a non-empty list"
                )
            overrides["pages"] = sorted(
                {
                    _positive_int(
                        page,
                        "config_overrides.pages[]",
                    )
                    for page in pages
                }
            )
        if "output_name" in overrides:
            _require_string(
                overrides["output_name"],
                "config_overrides.output_name",
            )
        object.__setattr__(
            self,
            "config_overrides",
            overrides,
        )
        if self.caller_reference is not None:
            _require_string(
                self.caller_reference,
                "caller_reference",
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "input": dict(self.input),
            "output_profile": self.output_profile.value,
            "config_overrides": dict(self.config_overrides),
        }
        if self.corrections is not None:
            result["corrections"] = self.corrections.to_dict()
        if self.caller_reference is not None:
            result["caller_reference"] = self.caller_reference
        return result

    def to_json(self) -> str:
        return canonical_json(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobRequest":
        _envelope(payload, SCHEMA_REQUEST)
        corrections = payload.get("corrections")
        if corrections is not None and not isinstance(corrections, Mapping):
            raise ContractValidationError("corrections must be an object")
        return cls(
            input=_object(payload.get("input"), "input"),
            output_profile=payload.get("output_profile", "final"),
            config_overrides=_object(
                payload.get("config_overrides"),
                "config_overrides",
            ),
            corrections=(
                CorrectionSet.from_dict(corrections)
                if isinstance(corrections, Mapping)
                else None
            ),
            caller_reference=payload.get("caller_reference"),
            schema=payload["schema"],
            contract_version=payload["contract_version"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "JobRequest":
        return cls.from_dict(
            _object(json.loads(raw), "job request")
        )


@dataclass(frozen=True)
class EngineError:
    category: ErrorCategory
    code: str
    public_message: str
    user_actionable: bool
    retryable: bool
    debug_context: Mapping[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA_ERROR
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "category",
            _enum(
                ErrorCategory,
                self.category,
                "error.category",
            ),
        )
        _require_string(self.code, "error.code")
        _require_string(
            self.public_message,
            "error.public_message",
        )
        if (
            not isinstance(self.user_actionable, bool)
            or not isinstance(self.retryable, bool)
        ):
            raise ContractValidationError(
                "error flags must be boolean"
            )
        object.__setattr__(
            self,
            "debug_context",
            _object(
                self.debug_context,
                "error.debug_context",
            ),
        )
        if (
            self.schema != SCHEMA_ERROR
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ContractValidationError(
                "unsupported engine error schema/version"
            )

    def to_dict(
        self,
        include_debug_context: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "category": self.category.value,
            "code": self.code,
            "public_message": self.public_message,
            "user_actionable": self.user_actionable,
            "retryable": self.retryable,
        }
        if include_debug_context and self.debug_context:
            result["debug_context"] = dict(self.debug_context)
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineError":
        _envelope(payload, SCHEMA_ERROR)
        return cls(
            category=payload.get("category"),
            code=payload.get("code"),
            public_message=payload.get("public_message"),
            user_actionable=payload.get("user_actionable"),
            retryable=payload.get("retryable"),
            debug_context=_object(
                payload.get("debug_context"),
                "error.debug_context",
            ),
            schema=payload["schema"],
            contract_version=payload["contract_version"],
        )


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: JobStatus
    provenance: Mapping[str, Any]
    pages: Mapping[str, Any]
    artifacts: tuple[ArtifactDescriptor, ...] = ()
    warnings: tuple[Mapping[str, Any], ...] = ()
    review: Mapping[str, Any] = field(
        default_factory=lambda: {
            "required": False,
            "reason_codes": [],
        }
    )
    failure: EngineError | None = None
    resources: Mapping[str, Any] | None = None
    caller_reference: str | None = None
    schema: str = SCHEMA_RESULT
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_string(self.job_id, "job_id")
        object.__setattr__(
            self,
            "status",
            _enum(JobStatus, self.status, "status"),
        )
        if (
            self.schema != SCHEMA_RESULT
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ContractValidationError(
                "unsupported job result schema/version"
            )

        provenance = _object(
            self.provenance,
            "provenance",
        )
        for key in (
            "engine_version",
            "pipeline_version",
            "source_commit",
        ):
            _require_string(
                provenance.get(key),
                f"provenance.{key}",
            )
        object.__setattr__(
            self,
            "provenance",
            provenance,
        )

        pages = _object(self.pages, "pages")
        for key in (
            "requested",
            "processed",
            "skipped",
        ):
            _nonnegative_int(
                pages.get(key),
                f"pages.{key}",
            )
        if (
            pages["processed"] + pages["skipped"]
            > pages["requested"]
        ):
            raise ContractValidationError(
                "processed + skipped must not exceed requested"
            )
        object.__setattr__(self, "pages", pages)

        artifacts = tuple(self.artifacts)
        if len(
            {artifact.artifact_id for artifact in artifacts}
        ) != len(artifacts):
            raise ContractValidationError(
                "duplicate artifact_id values are not allowed"
            )
        object.__setattr__(
            self,
            "artifacts",
            artifacts,
        )

        warnings = tuple(
            _object(warning, "warning")
            for warning in self.warnings
        )
        for warning in warnings:
            _require_string(
                warning.get("code"),
                "warning.code",
            )
            _require_string(
                warning.get("message"),
                "warning.message",
            )
        object.__setattr__(
            self,
            "warnings",
            warnings,
        )

        review = _object(self.review, "review")
        if not isinstance(
            review.get("required", False),
            bool,
        ):
            raise ContractValidationError(
                "review.required must be boolean"
            )
        object.__setattr__(self, "review", review)

        if (
            self.status
            in {JobStatus.FAILED, JobStatus.CANCELLED}
            and self.failure is None
        ):
            raise ContractValidationError(
                "failed/cancelled result requires failure"
            )
        if (
            self.status
            in {
                JobStatus.SUCCEEDED,
                JobStatus.REVIEW_REQUIRED,
            }
            and self.failure is not None
        ):
            raise ContractValidationError(
                "non-failure result must not include failure"
            )
        if (
            self.status is JobStatus.REVIEW_REQUIRED
            and not review.get("required")
        ):
            raise ContractValidationError(
                "review_required status requires "
                "review.required=true"
            )
        if (
            self.status is JobStatus.SUCCEEDED
            and review.get("required")
        ):
            raise ContractValidationError(
                "succeeded status cannot require review"
            )

        source_artifact_id = review.get(
            "correction_source_artifact_id"
        )
        artifact_ids = {
            artifact.artifact_id
            for artifact in artifacts
        }
        if (
            self.status is JobStatus.REVIEW_REQUIRED
            and source_artifact_id is None
        ):
            raise ContractValidationError(
                "review_required status requires "
                "correction_source_artifact_id"
            )
        if (
            source_artifact_id is not None
            and source_artifact_id not in artifact_ids
        ):
            raise ContractValidationError(
                "review correction source must reference "
                "a result artifact"
            )

        if self.resources is not None:
            resources = _object(
                self.resources,
                "resources",
            )
            for key, value in resources.items():
                valid = (
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and value >= 0
                    and math.isfinite(float(value))
                )
                if not valid:
                    raise ContractValidationError(
                        f"resources.{key} must be "
                        "finite and non-negative"
                    )
            object.__setattr__(
                self,
                "resources",
                resources,
            )

        if self.caller_reference is not None:
            _require_string(
                self.caller_reference,
                "caller_reference",
            )

    def to_dict(
        self,
        include_debug_context: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "job_id": self.job_id,
            "status": self.status.value,
            "provenance": dict(self.provenance),
            "pages": dict(self.pages),
            "artifacts": [
                artifact.to_dict()
                for artifact in self.artifacts
            ],
            "warnings": [
                dict(warning)
                for warning in self.warnings
            ],
            "review": dict(self.review),
        }
        if self.failure is not None:
            result["failure"] = self.failure.to_dict(
                include_debug_context
            )
        if self.resources is not None:
            result["resources"] = dict(self.resources)
        if self.caller_reference is not None:
            result["caller_reference"] = (
                self.caller_reference
            )
        return result

    def to_json(
        self,
        include_debug_context: bool = False,
    ) -> str:
        return canonical_json(
            self.to_dict(include_debug_context)
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobResult":
        _envelope(payload, SCHEMA_RESULT)
        artifacts = payload.get("artifacts", [])
        warnings = payload.get("warnings", [])
        if (
            not isinstance(artifacts, list)
            or not isinstance(warnings, list)
        ):
            raise ContractValidationError(
                "artifacts and warnings must be lists"
            )
        failure = payload.get("failure")
        if failure is not None and not isinstance(failure, Mapping):
            raise ContractValidationError("failure must be an object")
        return cls(
            job_id=payload.get("job_id"),
            status=payload.get("status"),
            provenance=_object(
                payload.get("provenance"),
                "provenance",
            ),
            pages=_object(
                payload.get("pages"),
                "pages",
            ),
            artifacts=tuple(
                ArtifactDescriptor.from_dict(artifact)
                for artifact in artifacts
            ),
            warnings=tuple(warnings),
            review=_object(
                payload.get("review"),
                "review",
            ),
            failure=(
                EngineError.from_dict(failure)
                if isinstance(failure, Mapping)
                else None
            ),
            resources=payload.get("resources"),
            caller_reference=payload.get(
                "caller_reference"
            ),
            schema=payload["schema"],
            contract_version=payload["contract_version"],
        )

    @classmethod
    def from_json(cls, raw: str) -> "JobResult":
        return cls.from_dict(
            _object(json.loads(raw), "job result")
        )


@dataclass(frozen=True)
class ProgressEvent:
    job_id: str
    sequence: int
    kind: ProgressKind
    stage_id: str
    page_number: int | None = None
    completed_units: int | None = None
    total_units: int | None = None
    unit: str | None = None
    schema: str = SCHEMA_PROGRESS
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_string(
            self.job_id,
            "progress.job_id",
        )
        _nonnegative_int(
            self.sequence,
            "progress.sequence",
        )
        object.__setattr__(
            self,
            "kind",
            _enum(
                ProgressKind,
                self.kind,
                "progress.kind",
            ),
        )
        if self.stage_id not in STAGE_IDS:
            raise ContractValidationError(
                "unknown progress stage_id: "
                f"{self.stage_id!r}"
            )
        if self.page_number is not None:
            _positive_int(
                self.page_number,
                "progress.page_number",
            )
        if (
            self.completed_units is None
        ) != (
            self.total_units is None
        ):
            raise ContractValidationError(
                "completed_units and total_units "
                "must be provided together"
            )
        if self.completed_units is not None:
            _nonnegative_int(
                self.completed_units,
                "progress.completed_units",
            )
            _positive_int(
                self.total_units,
                "progress.total_units",
            )
            if (
                self.completed_units
                > self.total_units
            ):
                raise ContractValidationError(
                    "completed_units must not exceed "
                    "total_units"
                )
            _require_string(
                self.unit,
                "progress.unit",
            )
        if (
            self.schema != SCHEMA_PROGRESS
            or self.contract_version != CONTRACT_VERSION
        ):
            raise ContractValidationError(
                "unsupported progress schema/version"
            )

    @property
    def terminal(self) -> bool:
        return self.kind in _TERMINAL_PROGRESS

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "job_id": self.job_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "stage_id": self.stage_id,
            "terminal": self.terminal,
        }
        for key in (
            "page_number",
            "completed_units",
            "total_units",
            "unit",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProgressEvent":
        _envelope(payload, SCHEMA_PROGRESS)
        event = cls(
            job_id=payload.get("job_id"),
            sequence=payload.get("sequence"),
            kind=payload.get("kind"),
            stage_id=payload.get("stage_id"),
            page_number=payload.get("page_number"),
            completed_units=payload.get("completed_units"),
            total_units=payload.get("total_units"),
            unit=payload.get("unit"),
            schema=payload["schema"],
            contract_version=payload["contract_version"],
        )
        if (
            "terminal" in payload
            and payload["terminal"] != event.terminal
        ):
            raise ContractValidationError(
                "progress.terminal disagrees "
                "with progress.kind"
            )
        return event


def validate_progress_sequence(
    events: Iterable[ProgressEvent],
) -> None:
    """Validate stream identity, monotonicity, and terminal semantics."""

    job_id: str | None = None
    previous_sequence: int | None = None
    terminal_seen = False

    for event in events:
        if job_id is None:
            job_id = event.job_id
        elif event.job_id != job_id:
            raise ContractValidationError(
                "progress stream must contain one job_id"
            )
        if (
            previous_sequence is not None
            and event.sequence <= previous_sequence
        ):
            raise ContractValidationError(
                "progress.sequence must be strictly increasing"
            )
        if terminal_seen:
            raise ContractValidationError(
                "no progress events are allowed after terminal"
            )
        terminal_seen = event.terminal
        previous_sequence = event.sequence


ProgressCallback = Callable[[ProgressEvent], None]


class JobExecutor(Protocol):
    """Direct Python boundary for CLI and worker/service adapters."""

    def __call__(
        self,
        request: JobRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> JobResult: ...
