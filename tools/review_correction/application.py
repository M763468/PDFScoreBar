"""Local application adapter for immutable, package-bound correction runs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from threading import Lock, Thread

from src.pipeline.review.apply_corrections import (
    _load_movement_boundary_input,
    _merge_existing_override_inputs,
    _read_existing_override_inputs,
    _resolve_source_manifest_path,
    _run_retained_artifact_correction,
    apply_corrections_and_rerun,
)
from src.pipeline.review.manual_correction_handoff import (
    canonicalize_manual_correction_outputs,
    load_manual_correction_handoff,
    validate_manual_correction_handoff,
)
from tools.review_correction.history import now


def preview_numbering(handoff_path: str | Path) -> dict:
    """Preview saved package corrections through the production numbering consumer."""
    handoff_path = Path(handoff_path).resolve()
    package_root = handoff_path.parent
    raw_handoff = load_manual_correction_handoff(handoff_path)
    normalized = validate_manual_correction_handoff(
        raw_handoff, handoff_path=handoff_path, mode="base_v1", require_existing_artifacts=True
    )
    manifest_path = _resolve_source_manifest_path(normalized, package_root)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Source manifest not found: {manifest_path}")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(source_manifest, dict) or not isinstance(source_manifest.get("config"), dict):
        raise ValueError("Source manifest must contain a config object")
    source_config = source_manifest["config"]
    source_root = manifest_path.parent
    staging_paths = {
        "mmr_measure_span": [],
        "measure_construction": [],
        "barline_construction": [],
    }
    for page in normalized.get("pages", []):
        for kind in staging_paths:
            raw_path = page.get("manual_outputs", {}).get(kind)
            if raw_path:
                staging_paths[kind].append(package_root / raw_path)

    existing = _read_existing_override_inputs(
        source_config=source_config,
        config_base_dir=manifest_path.parent,
    )
    with tempfile.TemporaryDirectory(prefix="pdfscore-numbering-preview-") as temporary:
        temporary_root = Path(temporary)
        movement_input = _load_movement_boundary_input(
            normalized_handoff=normalized,
            package_root=package_root,
            source_config=source_config,
            preview_output_path=temporary_root / "movement_boundaries.json",
        )
        canonical_paths = canonicalize_manual_correction_outputs(
            temporary_root / "corrections",
            overwrite=True,
            staging_paths=staging_paths,
        )
        _merge_existing_override_inputs(
            canonical_paths=canonical_paths,
            existing_override_inputs=existing,
            staging_paths=staging_paths,
        )
        corrected_run = temporary_root / "corrected"
        corrected_run.mkdir()
        _run_retained_artifact_correction(
            normalized_handoff=normalized,
            package_root=package_root,
            source_manifest=source_manifest,
            source_root=source_root,
            source_config=source_config,
            canonical_paths=canonical_paths,
            staging_paths=staging_paths,
            new_run_dir=corrected_run,
            movement_boundary_input=movement_input,
        )
        preview_pages = []
        for page in normalized.get("pages", []):
            page_id = str(page["page_id"])
            page_number = int(page["page_number"])
            output_path = corrected_run / "outputs" / page_id / "numbering_final.json"
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            page_data = (payload.get("pages") or [payload])[0]
            systems = []
            for system_index, system in enumerate(page_data.get("systems", [])):
                measures = system.get("measures", [])
                numbered = [
                    measure.get("number")
                    for measure in measures
                    if isinstance(measure, dict) and measure.get("number") is not None
                ]
                if numbered:
                    systems.append(
                        {
                            "system": system.get("index", system.get("system", system_index)),
                            "first_measure_number": numbered[0],
                            "measure_count": len(numbered),
                        }
                    )
            preview_pages.append(
                {
                    "page": page_number - 1,
                    "page_number": page["source_page_number_one_based"],
                    "page_id": page_id,
                    "systems": systems,
                }
            )
        return {
            "status": "provisional",
            "basis": "saved_review_corrections",
            "pages": preview_pages,
        }


class CorrectionApplication:
    def __init__(self, package, handoff: Path):
        self.package = package
        self.handoff = handoff.resolve()
        self.root = package.root / "application_runs"
        self.lock = Lock()
        self.thread = None
        self.process_lock = None

    def _safe_root(self):
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError("Application output directory must stay in the review package")
        self.root.mkdir(exist_ok=True)

    def start(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A corrected result is already being generated")
        apply_started = False
        attempt = None
        event = {}
        try:
            self._safe_root()
            descriptor = os.open(
                self.root / ".apply.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            self.process_lock = os.fdopen(descriptor, "r+")
            try:
                fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(
                    "A corrected result is already being generated for this package"
                ) from exc
            with self.package.history.transaction(allow_apply=True):
                checkpoint = self.package.history.capture()
                identity = self.package.state.begin_apply()
                apply_started = True
                if self.package.history.get(checkpoint)["identity"] != identity:
                    raise ValueError("Review changed while preparing application")
                attempt = self._allocate()
                event = {
                    "status": "running",
                    "checkpoint_id": checkpoint,
                    "identity": identity,
                    "started_at": now(),
                }
                self.package.history.application_record(attempt.name, event)
            response = self.package.state.snapshot()
            self.thread = Thread(
                target=self._run, args=(identity, checkpoint, attempt, event), daemon=True
            )
            self.thread.start()
            return response
        except Exception as exc:
            if apply_started:
                self._fail_apply(exc, attempt, event)
            if self.process_lock is not None:
                self.process_lock.close()
                self.process_lock = None
            self.lock.release()
            raise

    def _allocate(self):
        # Stable monotonic names, including failed attempts; never reuse an existing run.
        number = 1
        while True:
            attempt = self.root / f"attempt_{number:04d}"
            try:
                attempt.mkdir()
                return attempt
            except FileExistsError:
                number += 1

    def _fail_apply(self, error, attempt, event):
        self.package.state.fail_apply(str(error))
        if attempt is not None:
            try:
                self.package.history.application_record(
                    attempt.name,
                    {**event, "status": "failed", "finished_at": now(), "error": str(error)[:500]},
                )
            except (OSError, ValueError):
                # The package error remains authoritative if journal storage fails.
                pass

    def _run(self, identity, checkpoint, attempt, event):
        try:
            review = attempt / "input_review"
            self.package.history.materialize(checkpoint, review)
            payload = json.loads((review / "manual_correction_input.json").read_text())
            if not self.package.history.get(checkpoint).get("source_context"):
                manifest = _resolve_source_manifest_path(payload, self.package.root)
                payload["source_manifest"] = str(manifest)
            if not (isinstance(payload.get("output_name"), str) and payload["output_name"].strip()):
                final_dir = self.package.root.parent / "final"
                if final_dir.is_dir():
                    from src.pipeline.review.final_output import (
                        _is_usable_artifact_root_name,
                        _sanitize_output_name,
                    )

                    final_pdfs = sorted(
                        path
                        for path in final_dir.glob("*_score_numbered.pdf")
                        if path.is_file() and not path.is_symlink()
                    )
                    if len(final_pdfs) == 1:
                        recovered_name = _sanitize_output_name(final_pdfs[0].name, fallback="")
                        if (
                            recovered_name
                            and _is_usable_artifact_root_name(recovered_name)
                            and recovered_name.lower() != "score"
                        ):
                            payload["output_name"] = recovered_name
            snapshot_handoff = review / "manual_correction_input.json"
            snapshot_handoff.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            if self.package.state.capture_identity() != identity:
                raise ValueError("Review inputs changed while preparing the corrected run")
            provenance = {
                **identity,
                "source_handoff": str(self.handoff),
                "snapshot_handoff": str(snapshot_handoff),
                "checkpoint_id": checkpoint,
            }
            (attempt / "consumed_inputs.json").write_text(
                json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
            )
            resume = payload.get("resume")
            run = apply_corrections_and_rerun(
                snapshot_handoff,
                output_root=attempt,
                run_id="corrected",
                overwrite=False,
                generate_final_pdf=not bool(resume),
            )
            layer_identity = {}
            if resume:
                from src.pipeline.review.number_layer import records_from_run, write_number_layer
                from tools.review_correction.history import package_path

                annotated = package_path(review, resume["input_pdf"])
                if hashlib.sha256(annotated.read_bytes()).hexdigest() != resume["input_sha256"]:
                    raise ValueError("Annotated input changed after resume")
                if resume.get("background_pdf"):
                    annotated = package_path(review, resume["background_pdf"])
                    if (
                        hashlib.sha256(annotated.read_bytes()).hexdigest()
                        != resume["background_sha256"]
                    ):
                        raise ValueError("Normalized annotated background changed after resume")
                final_dir = run / "final"
                final_dir.mkdir(exist_ok=True)
                numbered = final_dir / "annotated_score_numbered.pdf"
                write_number_layer(
                    annotated, annotated, records_from_run(snapshot_handoff, run), numbered
                )
                sidecar = numbered.with_suffix(".layer.json")
                layer_identity = {
                    "number_layer_sidecar": str(sidecar.resolve()),
                    "number_layer_sidecar_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
                    "resume_checkpoint_id": resume["checkpoint_id"],
                    "resume_input_sha256": resume["input_sha256"],
                    "removed_returned_number_count": (resume.get("roundtrip") or {}).get(
                        "removed_number_count", 0
                    ),
                }
                summary_path = run / "review/correction_summary.json"
                report = json.loads(summary_path.read_text())
                report["final_pdf"] = str(numbered.resolve())
                summary_path.write_text(json.dumps(report, indent=2) + "\n")
            summary = json.loads(
                (run / "review" / "correction_summary.json").read_text(encoding="utf-8")
            )
            final = Path(summary.get("final_pdf") or "").resolve()
            if not final.is_file() or (run / "final").resolve() not in final.parents:
                raise ValueError("The corrected final PDF was not generated")
            data = final.read_bytes()
            if not data.startswith(b"%PDF-"):
                raise ValueError("The corrected output is not a PDF")
            movement_inputs = {
                rel: hashlib.sha256((review / rel).read_bytes()).hexdigest()
                for page in self.package.pages
                if (rel := page.get("movement_boundary_resolved_output"))
                and (review / rel).is_file()
            }
            self.package.history.validate_dependencies(checkpoint)
            result = self.package.state.finish_apply(
                {
                    **identity,
                    "source_handoff": str(self.handoff),
                    "checkpoint_id": checkpoint,
                    "consumed_inputs": str(attempt / "consumed_inputs.json"),
                    "movement_review_inputs": movement_inputs,
                    **layer_identity,
                },
                corrected_run=str(run.resolve()),
                final_pdf=str(final),
                final_pdf_sha256=hashlib.sha256(data).hexdigest(),
            )
            self.package.history.application_record(
                attempt.name,
                {**event, "status": "succeeded", "finished_at": now(), "result": result},
            )
        except Exception as exc:
            self._fail_apply(exc, attempt, event)
        finally:
            if self.process_lock is not None:
                self.process_lock.close()
                self.process_lock = None
            self.lock.release()

    def result(self):
        result = self.package.state.snapshot()["package"]["last_successful_result"]
        if not result:
            raise ValueError("No corrected final PDF has been generated")
        final = Path(result["final_pdf"])
        self._safe_root()
        if final.resolve() != final or self.root not in final.parents or not final.is_file():
            raise ValueError("The corrected final PDF is unavailable")
        if hashlib.sha256(final.read_bytes()).hexdigest() != result["final_pdf_sha256"]:
            raise ValueError("The corrected final PDF changed after generation")
        if result.get("number_layer_sidecar"):
            sidecar = Path(result["number_layer_sidecar"])
            if (
                sidecar.resolve() != sidecar
                or sidecar.parent != final.parent
                or hashlib.sha256(sidecar.read_bytes()).hexdigest()
                != result["number_layer_sidecar_sha256"]
            ):
                raise ValueError("The validated numbering sidecar changed")
        return final
