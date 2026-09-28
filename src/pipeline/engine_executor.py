"""Versioned one-job adapter over the current config-first pipeline."""

from __future__ import annotations

import errno
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from src.pipeline.engine_contract import (
    ArtifactDescriptor,
    ContractValidationError,
    EngineError,
    ErrorCategory,
    JobRequest,
    JobResult,
    JobStatus,
    OutputProfile,
    ProgressCallback,
    ProgressKind,
)
from src.pipeline.engine_input_safety import (
    DEFAULT_JOB_SAFETY_POLICY,
    InputSafetyError,
    JobSafetyPolicy,
    enforce_attempt_disk_budget,
    resolve_local_input_path,
    validate_local_pdf,
    validate_output_name,
)
from src.pipeline.engine_telemetry import TelemetryRecorder

REVIEW_COORDINATE_SPACE = {
    "type": "rendered_page_image",
    "origin": "top_left",
    "units": "pixels",
    "version": "1",
}
PIPELINE_VERSION = "dense_full_pipeline.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attempt_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        try:
            if path.is_symlink():
                continue
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            continue
    return total


def _check_attempt_budget(root: Path, policy: JobSafetyPolicy) -> None:
    enforce_attempt_disk_budget(_attempt_bytes(root), policy=policy)


def _source_commit(explicit: str | None) -> str:
    if explicit:
        return explicit
    if value := os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT"):
        return value
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _engine_version() -> str:
    try:
        return importlib.metadata.version("pdfscore-pipeline")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def _error(
    category: ErrorCategory,
    code: str,
    message: str,
    *,
    actionable: bool,
    retryable: bool,
    exc: BaseException | None = None,
) -> EngineError:
    debug = {}
    if exc is not None:
        debug = {"exception": type(exc).__name__, "message": str(exc)}
    return EngineError(
        category=category,
        code=code,
        public_message=message,
        user_actionable=actionable,
        retryable=retryable,
        debug_context=debug,
    )


def _map_error(exc: BaseException) -> EngineError:
    if isinstance(exc, InputSafetyError):
        return exc.to_engine_error()
    if isinstance(exc, ContractValidationError):
        return _error(
            ErrorCategory.INVALID_REQUEST,
            "request_invalid",
            "The engine job request is invalid.",
            actionable=True,
            retryable=False,
            exc=exc,
        )
    if isinstance(exc, subprocess.CalledProcessError):
        return _error(
            ErrorCategory.INTERNAL,
            "child_process_failed",
            "A required engine subprocess failed.",
            actionable=False,
            retryable=True,
            exc=exc,
        )
    if isinstance(exc, FileNotFoundError):
        return _error(
            ErrorCategory.DEPENDENCY,
            "runtime_dependency_unavailable",
            "A required engine runtime dependency is unavailable.",
            actionable=False,
            retryable=True,
            exc=exc,
        )
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return _error(
            ErrorCategory.RESOURCE,
            "disk_capacity_exhausted",
            "The engine ran out of temporary storage.",
            actionable=False,
            retryable=True,
            exc=exc,
        )
    return _error(
        ErrorCategory.INTERNAL,
        "internal_error",
        "The engine could not complete the job.",
        actionable=False,
        retryable=True,
        exc=exc,
    )


class PipelineJobExecutor:
    """Synchronous JobExecutor backed by src.pipeline.main.run_pipeline."""

    def __init__(
        self,
        *,
        input_root: str | Path,
        artifact_root: str | Path,
        base_config_path: str | Path = "configs/dense_full_pipeline.yaml",
        safety_policy: JobSafetyPolicy = DEFAULT_JOB_SAFETY_POLICY,
        source_commit: str | None = None,
        job_id_factory: Callable[[], str] | None = None,
        engine_ref_resolver: Callable[[str], str | Path] | None = None,
        pipeline_runner: Callable[..., Path] | None = None,
        review_materializer: Callable[..., Mapping[str, Any]] | None = None,
        final_materializer: Callable[..., Mapping[str, Any]] | None = None,
        sample_resources: bool = False,
    ) -> None:
        self.input_root = Path(input_root).resolve()
        self.artifact_root = Path(artifact_root).resolve()
        self.base_config_path = Path(base_config_path)
        self.safety_policy = safety_policy
        self.source_commit = _source_commit(source_commit)
        self.job_id_factory = job_id_factory or (lambda: f"job-{uuid.uuid4().hex}")
        self.engine_ref_resolver = engine_ref_resolver
        self.pipeline_runner = pipeline_runner
        self.review_materializer = review_materializer
        self.final_materializer = final_materializer
        self.sample_resources = sample_resources

    def __call__(
        self, request: JobRequest, *, on_progress: ProgressCallback | None = None
    ) -> JobResult:
        return self._execute(request, self._new_job_id(), on_progress)

    def execute_payload(
        self,
        payload: Mapping[str, Any] | str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> JobResult:
        """Parse untrusted wire input and return a structured failure on parse errors."""
        job_id = self._new_job_id()
        try:
            request = (
                JobRequest.from_json(payload)
                if isinstance(payload, str)
                else JobRequest.from_dict(payload)
            )
        except Exception as exc:
            return self._early_failure(
                job_id,
                None,
                _error(
                    ErrorCategory.INVALID_REQUEST,
                    "request_invalid",
                    "The engine job request is invalid.",
                    actionable=True,
                    retryable=False,
                    exc=exc,
                ),
                on_progress,
            )
        return self._execute(request, job_id, on_progress)

    def _new_job_id(self) -> str:
        value = self.job_id_factory()
        if (
            not isinstance(value, str)
            or not value.strip()
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
        ):
            raise ValueError("job_id_factory must return a safe non-empty identifier")
        return value

    def _provenance(self) -> dict[str, str]:
        return {
            "engine_version": _engine_version(),
            "pipeline_version": PIPELINE_VERSION,
            "source_commit": self.source_commit,
        }

    def _load_config(self) -> dict[str, Any]:
        from src.pipeline.core.config import load_yaml

        return deepcopy(load_yaml(self.base_config_path))

    @staticmethod
    def _dpi(config: Mapping[str, Any]) -> float:
        inputs = config.get("inputs")
        if isinstance(inputs, Mapping):
            pdf = inputs.get("pdf_to_images")
            if isinstance(pdf, Mapping) and pdf.get("dpi") is not None:
                return float(pdf["dpi"])
        return 300.0

    def _input_reference(self, request: JobRequest) -> str:
        reference = str(request.input["reference"])
        if request.input["kind"] == "local_path":
            return reference
        if self.engine_ref_resolver is None:
            raise ContractValidationError("engine_ref requires an engine-owned resolver")
        return str(self.engine_ref_resolver(reference))

    def _write_config(
        self,
        config: dict[str, Any],
        *,
        input_path: Path,
        pages: tuple[int, ...],
        job_id: str,
        work_root: Path,
    ) -> Path:
        from src.pipeline.core.config import write_yaml

        run = config.setdefault("run", {})
        inputs = config.setdefault("inputs", {})
        steps = config.setdefault("steps", {})
        outputs = config.setdefault("outputs", {})
        if not all(isinstance(item, dict) for item in (run, inputs, steps, outputs)):
            raise ValueError("base config run/inputs/steps/outputs sections must be mappings")

        run["run_id"] = job_id
        run["output_root"] = str(work_root / "runs")
        inputs["pdf_path"] = str(input_path)
        pdf = deepcopy(inputs.get("pdf_to_images") or {})
        if not isinstance(pdf, dict):
            raise ValueError("base config inputs.pdf_to_images must be a mapping")
        pdf.update(
            {
                "dpi": self._dpi(config),
                "pages": ",".join(str(page) for page in pages),
                "target_width": None,
                "target_height": None,
                "interpolation": "area",
                "prefix": "page",
                "format": "png",
                "overwrite": True,
                "alpha": False,
                "image_glob": "page_*.png",
            }
        )
        pdf.pop("output_dir", None)
        inputs["pdf_to_images"] = pdf
        steps["pdf_to_images"] = True

        detection = config.get("detection")
        if isinstance(detection, dict):
            detection["hybrid_output_root"] = str(work_root / "runs" / job_id / "hybrid_output")

        review = outputs.setdefault("review", {})
        if not isinstance(review, dict):
            raise ValueError("base config outputs.review must be a mapping")
        review.update(
            {
                "manual_correction_package": True,
                "root": ".review_work",
                "overwrite": True,
            }
        )

        path = work_root / "request.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(path, config)
        return path

    def _runner(self) -> Callable[..., Path]:
        if self.pipeline_runner is not None:
            return self.pipeline_runner
        from src.pipeline.main import run_pipeline

        return run_pipeline

    def _review_builder(self) -> Callable[..., Mapping[str, Any]]:
        if self.review_materializer is not None:
            return self.review_materializer
        from src.pipeline.review.manual_correction_materializer import (
            materialize_manual_correction_review_package,
        )

        return materialize_manual_correction_review_package

    def _final_builder(self) -> Callable[..., Mapping[str, Any]]:
        if self.final_materializer is not None:
            return self.final_materializer
        from src.pipeline.review.final_output import materialize_corrected_final_outputs

        return materialize_corrected_final_outputs

    def _execute(
        self,
        request: JobRequest,
        job_id: str,
        on_progress: ProgressCallback | None,
    ) -> JobResult:
        package_root = self.artifact_root / job_id
        work_root = package_root / ".engine-work"
        staging = work_root / "publish"
        telemetry: TelemetryRecorder | None = None
        requested = 0

        # Correction execution needs an engine-owned retained-source resolver. Fail
        # closed until that source identity has been validated; never rerun the raw
        # input as though the submitted corrections had been applied.
        if request.corrections is not None:
            return self._early_failure(
                job_id,
                request.caller_reference,
                _error(
                    ErrorCategory.CORRECTION,
                    "correction_execution_unavailable",
                    "The correction source cannot be resolved by this executor.",
                    actionable=True,
                    retryable=False,
                ),
                on_progress,
            )

        try:
            config = self._load_config()
            reference = self._input_reference(request)
            resolved = resolve_local_input_path(
                reference, allowed_root=self.input_root, policy=self.safety_policy
            )
            meta = validate_local_pdf(
                str(resolved),
                allowed_root=self.input_root,
                requested_pages=request.config_overrides.get("pages"),
                render_dpi=self._dpi(config),
                policy=self.safety_policy,
            )
            source_name = meta.source_name
            requested = len(meta.selected_pages)
            expected_sha = request.input.get("sha256")
            if expected_sha is not None and expected_sha != meta.sha256:
                raise InputSafetyError(
                    category=ErrorCategory.INPUT,
                    code="input_pdf_identity_mismatch",
                    public_message="The input PDF does not match the requested identity.",
                    user_actionable=True,
                    retryable=False,
                )

            work_root.mkdir(parents=True, exist_ok=True)
            staged_input = work_root / "input" / "source.pdf"
            staged_input.parent.mkdir(parents=True, exist_ok=True)
            with resolved.open("rb") as source, staged_input.open("wb") as target:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > self.safety_policy.max_pdf_bytes:
                        raise InputSafetyError(
                            category=ErrorCategory.RESOURCE,
                            code="input_pdf_too_large",
                            public_message="The input PDF exceeds the configured size limit.",
                            user_actionable=True,
                            retryable=False,
                        )
                    target.write(chunk)
            staged_meta = validate_local_pdf(
                str(staged_input),
                allowed_root=staged_input.parent,
                requested_pages=request.config_overrides.get("pages"),
                render_dpi=self._dpi(config),
                policy=self.safety_policy,
            )
            if staged_meta.sha256 != meta.sha256:
                raise InputSafetyError(
                    category=ErrorCategory.INPUT,
                    code="input_pdf_changed_during_staging",
                    public_message="The input PDF changed while it was being staged.",
                    user_actionable=True,
                    retryable=False,
                )
            meta = staged_meta
            requested = len(meta.selected_pages)
            _check_attempt_budget(work_root, self.safety_policy)

            output_name = validate_output_name(
                str(request.config_overrides.get("output_name") or Path(source_name).stem)
            )
            self._clear_public(package_root)
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)
            config_path = self._write_config(
                config,
                input_path=staged_input,
                pages=meta.selected_pages,
                job_id=job_id,
                work_root=work_root,
            )

            telemetry = TelemetryRecorder(
                job_id, on_progress=on_progress, sample_resources=self.sample_resources
            )
            telemetry.start_job()
            run_dir = Path(
                self._runner()(
                    config_path,
                    run_id=job_id,
                    output_root=work_root / "runs",
                    debug=request.output_profile is OutputProfile.DEBUG,
                    telemetry_recorder=telemetry,
                )
            )
            _check_attempt_budget(work_root, self.safety_policy)

            internal_handoff = run_dir / ".review_work" / "manual_correction_input.json"
            if not internal_handoff.is_file():
                self._review_builder()(
                    run_root=run_dir,
                    review_root=internal_handoff.parent,
                    overwrite=True,
                )
            if not internal_handoff.is_file():
                raise RuntimeError("review materializer did not produce its handoff")

            with telemetry.stage("artifact_materialization", detail_code="engine.public_artifacts"):
                public_review = None
                if request.output_profile in {OutputProfile.REVIEW, OutputProfile.DEBUG}:
                    public_review = staging / "review"
                    self._copy_review(internal_handoff.parent, public_review, source_job_id=job_id)

                final_summary = self._final_builder()(
                    handoff_path=internal_handoff,
                    corrected_run_dir=run_dir,
                    final_root=staging / "final",
                    review_root=work_root / ".final_summary",
                    output_name=output_name,
                )
                final_pdf = Path(str(final_summary["final_pdf"]))
                final_root = (staging / "final").resolve()
                final_pdf = final_pdf.resolve()
                if not final_pdf.is_relative_to(final_root):
                    raise RuntimeError("final materializer returned a path outside final output")
                if not final_pdf.is_file():
                    raise RuntimeError("final materializer did not produce a PDF")

            _check_attempt_budget(work_root, self.safety_policy)
            if request.output_profile is OutputProfile.DEBUG:
                debug_root = staging / "debug" / job_id
                debug_root.mkdir(parents=True, exist_ok=True)
                (debug_root / "telemetry.json").write_text(
                    json.dumps(
                        telemetry.summary(),
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )

            pages = self._page_summary(run_dir, requested)
            artifacts = self._artifacts(staging, final_pdf, request.output_profile, job_id)
            self._publish(staging, package_root)
            telemetry.terminal(JobStatus.SUCCEEDED)
            warnings = tuple(
                {"code": "final_materialization_warning", "message": str(message)}
                for message in final_summary.get("warnings", [])
            )
            if request.output_profile in {OutputProfile.REVIEW, OutputProfile.DEBUG}:
                retained = package_root / ".engine-retained"
                if retained.exists():
                    shutil.rmtree(retained)
                work_root.replace(retained)
            else:
                shutil.rmtree(work_root, ignore_errors=True)
            return JobResult(
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                provenance=self._provenance(),
                pages=pages,
                artifacts=artifacts,
                warnings=warnings,
                review={"required": False, "reason_codes": []},
                resources=telemetry.job_resources(),
                caller_reference=request.caller_reference,
            )
        except Exception as exc:
            self._clear_public(package_root)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(work_root, ignore_errors=True)
            shutil.rmtree(package_root / ".engine-retained", ignore_errors=True)
            failure = _map_error(exc)
            if telemetry is None:
                return self._early_failure(
                    job_id,
                    request.caller_reference,
                    failure,
                    on_progress,
                    requested=requested,
                )
            telemetry.terminal(JobStatus.FAILED)
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                provenance=self._provenance(),
                pages={"requested": requested, "processed": 0, "skipped": 0},
                artifacts=(),
                warnings=(),
                review={"required": False, "reason_codes": []},
                failure=failure,
                resources=telemetry.job_resources(),
                caller_reference=request.caller_reference,
            )

    def _early_failure(
        self,
        job_id: str,
        caller_reference: str | None,
        failure: EngineError,
        on_progress: ProgressCallback | None,
        *,
        requested: int = 0,
    ) -> JobResult:
        telemetry = TelemetryRecorder(job_id, on_progress=on_progress)
        telemetry.start_job()
        telemetry.emit(
            ProgressKind.STAGE_STARTED,
            "input_validation",
            detail_code="engine.request_preflight",
        )
        telemetry.terminal(JobStatus.FAILED)
        return JobResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            provenance=self._provenance(),
            pages={"requested": requested, "processed": 0, "skipped": 0},
            artifacts=(),
            warnings=(),
            review={"required": False, "reason_codes": []},
            failure=failure,
            resources=telemetry.job_resources(),
            caller_reference=caller_reference,
        )

    @staticmethod
    def _clear_public(package_root: Path) -> None:
        for name in ("final", "review", "debug"):
            path = package_root / name
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    @staticmethod
    def _copy_review(source: Path, destination: Path, *, source_job_id: str) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        handoff_path = destination / "manual_correction_input.json"
        payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("manual correction handoff must be an object")
        for key in ("source_artifact_root", "source_manifest", "source_pipeline_command"):
            payload.pop(key, None)
        payload["engine_contract_version"] = "1"
        payload["source_job_id"] = source_job_id
        payload["coordinate_space"] = dict(REVIEW_COORDINATE_SPACE)
        for page in payload.get("pages", []):
            if isinstance(page, dict):
                for key in (
                    "barlines_review_source",
                    "barlines_review_source_kind",
                    "barlines_review_source_manifest_field",
                ):
                    page.pop(key, None)
        handoff_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _page_summary(run_dir: Path, requested: int) -> dict[str, int]:
        payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            raise ValueError("pipeline manifest pages must be a list")
        skipped = 0
        for page in pages:
            status = page.get("status") if isinstance(page, dict) else None
            if isinstance(status, dict) and (
                status.get("excluded_by_user") is True
                or status.get("blank_page") is True
                or status.get("staff_detect_failed") is True
            ):
                skipped += 1
        skipped = min(skipped, requested)
        return {"requested": requested, "processed": requested - skipped, "skipped": skipped}

    @staticmethod
    def _artifacts(
        staging: Path, final_pdf: Path, profile: OutputProfile, job_id: str
    ) -> tuple[ArtifactDescriptor, ...]:
        final_pdf = final_pdf.resolve()
        artifacts = [
            ArtifactDescriptor(
                artifact_id="final.pdf",
                role="final.score_numbered_pdf",
                location_kind="relative_path",
                reference=(
                    "final/" + final_pdf.relative_to((staging / "final").resolve()).as_posix()
                ),
                media_type="application/pdf",
                sha256=_sha256(final_pdf),
            )
        ]
        if profile in {OutputProfile.REVIEW, OutputProfile.DEBUG}:
            handoff = staging / "review" / "manual_correction_input.json"
            artifacts.append(
                ArtifactDescriptor(
                    artifact_id="review.manual_correction_input",
                    role="review.manual_correction_input",
                    location_kind="relative_path",
                    reference="review/manual_correction_input.json",
                    media_type="application/json",
                    sha256=_sha256(handoff),
                    coordinate_space=REVIEW_COORDINATE_SPACE,
                )
            )
        if profile is OutputProfile.DEBUG:
            telemetry = staging / "debug" / job_id / "telemetry.json"
            artifacts.append(
                ArtifactDescriptor(
                    artifact_id="debug.telemetry",
                    role="debug.telemetry_summary",
                    location_kind="relative_path",
                    reference=f"debug/{job_id}/telemetry.json",
                    media_type="application/json",
                    sha256=_sha256(telemetry),
                )
            )
        return tuple(artifacts)

    @staticmethod
    def _publish(staging: Path, package_root: Path) -> None:
        for name in ("final", "review", "debug"):
            source = staging / name
            if source.exists():
                destination = package_root / name
                if destination.exists():
                    raise FileExistsError(f"public artifact destination already exists: {name}")
                source.replace(destination)
        shutil.rmtree(staging, ignore_errors=True)
