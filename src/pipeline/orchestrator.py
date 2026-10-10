"""Pipeline orchestration for end-to-end processing."""

from __future__ import annotations

import hashlib
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import torch
from tqdm import tqdm

from src.pdf_to_images import normalise_pages
from src.pipeline.core import ensure_dir, get_nested, load_json, score_to_dict, write_json
from src.pipeline.core.manifest import build_manifest
from src.pipeline.detection import (
    resolve_barlines_and_masks_config,
    resolve_paths_from_detection,
    run_detection_step,
)
from src.pipeline.engine_telemetry import TelemetryRecorder
from src.pipeline.review.manual_correction_materializer import (
    materialize_manual_correction_review_package,
)
from src.pipeline.review.pipeline_review import (
    ReviewPackageConfig as _ReviewPackageConfig,
)
from src.pipeline.review.pipeline_review import (
    resolve_review_package_config,
    resolved_for_manifest,
    validate_review_package_prerequisites,
)
from src.pipeline.steps import numbering_phases
from src.pipeline.steps.barlines import (
    apply_barline_overrides,
    merge_measure_overrides,
    normalize_barlines,
)
from src.pipeline.steps.filters import get_user_exclude_indices, resolve_page_filters
from src.pipeline.steps.numbering import (
    FINAL_NUMBERING_SCHEMA_VERSION,
    SYSTEM_INDEX_CONTRACT,
    empty_numbering_payload,
    final_numbering_metadata,
    load_movement_boundary_payload,
    movement_boundaries_for_page,
    persisted_final_next_number,
    rebase_mmr_overrides_to_page_local,
    reject_movement_boundaries_on_excluded_pages,
    run_mmr_batch,
)
from src.pipeline.steps.numbering_phases import NumberingPhaseServices
from src.pipeline.utils.images import (
    collect_images,
    resolve_page_ids,
    resolve_source_page_references,
)

logger = logging.getLogger(__name__)

# Persistence: Cache HomrPredictor and other heavy models to avoid re-loading.
_PIPELINE_PERSISTENCE: Dict[str, Any] = {}
# MMR Persistence: Cache MMRClassifier and MMROCREngine to avoid re-loading models.
_MMR_PERSISTENCE: Dict[Any, Any] = {}


class PipelineOrchestrator:
    """Orchestrates the different phases of the numbering pipeline."""

    def __init__(
        self,
        config: Dict[str, Any],
        run_id: str,
        run_dir: Path,
        dry_run: bool = False,
        validate_only: bool = False,
        skip_existing: bool = False,
        debug: bool = False,
        telemetry: TelemetryRecorder | None = None,
    ):
        self.config = config
        self.run_id = run_id
        self.run_dir = run_dir
        self.dry_run = dry_run
        self.validate_only = validate_only
        self.skip_existing = skip_existing
        self.debug = debug
        self.telemetry = telemetry
        self._movement_boundaries: Dict[str, Any] | None = None
        self._barline_override_payload: Dict[str, Any] | None = None

        self.intermediate_dir = run_dir / "intermediate"
        self.outputs_dir = run_dir / "outputs"

        # Persistence: Link to module-level cache
        self._persistence = _PIPELINE_PERSISTENCE
        self._mmr_persistence = _MMR_PERSISTENCE

    def _telemetry_stage(self, stage_id: str, *, detail_code: str | None = None):
        if self.telemetry is None:
            return nullcontext()
        return self.telemetry.stage(stage_id, detail_code=detail_code)

    def _telemetry_progress(
        self,
        stage_id: str,
        *,
        page_number: int | None = None,
        completed_units: int | None = None,
        total_units: int | None = None,
        unit: str | None = None,
        detail_code: str | None = None,
    ) -> None:
        if self.telemetry is None:
            return
        self.telemetry.progress(
            stage_id,
            page_number=page_number,
            completed_units=completed_units,
            total_units=total_units,
            unit=unit,
            detail_code=detail_code,
        )

    def _validate_input_prerequisites(
        self,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Validate required external inputs before input_validation completes."""
        self._validate_review_package_prerequisites()

        pdf_opts = get_nested(self.config, "inputs", "pdf_to_images", default={}) or {}
        render_pdf = bool(get_nested(self.config, "steps", "pdf_to_images", default=False))
        if render_pdf:
            pdf_path = get_nested(self.config, "inputs", "pdf_path")
            if not pdf_path:
                raise ValueError("inputs.pdf_path is required when pdf_to_images is enabled.")
            skip_render = (
                self.skip_existing
                and (self.run_dir / "inputs" / "images").exists()
                and list((self.run_dir / "inputs" / "images").glob("*.png"))
            )
            if not skip_render and not self.dry_run and not Path(pdf_path).is_file():
                raise FileNotFoundError(f"PDF input not found: {pdf_path}")
        else:
            self._validate_external_image_inputs(pdf_opts)

        user_overrides_path = get_nested(self.config, "inputs", "measure_overrides")
        user_overrides_payload = (
            load_json(Path(user_overrides_path)) if user_overrides_path else None
        )

        barline_overrides_path = get_nested(self.config, "inputs", "barline_overrides")
        self._barline_override_payload = (
            load_json(Path(barline_overrides_path)) if barline_overrides_path else None
        )

        movement_boundaries = load_movement_boundary_payload(
            get_nested(self.config, "inputs", "movement_boundaries")
        )
        return user_overrides_payload, movement_boundaries

    def _validate_external_image_inputs(self, pdf_opts: Dict[str, Any]) -> None:
        """Mirror collect_images discovery without staging/copying external files."""
        output_dir = self.run_dir / "inputs" / "images"
        image_glob = pdf_opts.get("image_glob", "page_*.png")
        external_dir = pdf_opts.get("output_dir")

        if not output_dir.exists():
            if external_dir:
                output_dir = Path(external_dir)
            else:
                raise ValueError(
                    "PDF images not found. Enable pdf_to_images or specify output_dir."
                )

        images = sorted(Path(output_dir).glob(image_glob))
        if not images and external_dir:
            external_path = Path(external_dir)
            images = sorted(external_path.glob(image_glob))
            output_dir = external_path
        if not images:
            raise FileNotFoundError(f"No images found in {output_dir} matching {image_glob}")

    def _run_pdf_to_images(self) -> tuple[str, list[int]] | None:
        """Step 1: Convert PDF to images in-process and retain exact source identity."""
        pdf_path = get_nested(self.config, "inputs", "pdf_path")
        pdf_opts = get_nested(self.config, "inputs", "pdf_to_images", default={}) or {}
        if not pdf_path:
            raise ValueError("inputs.pdf_path is required when pdf_to_images is enabled.")

        output_dir = self.run_dir / "inputs" / "images"
        ensure_dir(output_dir)

        if self.dry_run:
            logger.info(f"Executing (dry-run): render_pdf {pdf_path} -> {output_dir}")
            return None

        import fitz

        pdf_path = Path(pdf_path)
        source_bytes = pdf_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        with fitz.open(stream=source_bytes, filetype="pdf") as doc:
            pages = normalise_pages(pdf_opts.get("pages"), doc.page_count)

        logger.info(f"Rendering PDF: {pdf_path} (pages: {pages}) -> {output_dir}")
        from src.pdf_to_images import render_pdf_to_memory
        from src.pipeline.utils.images import get_image_cache

        def report_render_progress(completed: int, _source_page_index: int) -> None:
            self._telemetry_progress(
                "pdf_render",
                page_number=completed,
                completed_units=completed,
                total_units=len(pages),
                unit="page",
                detail_code="pdf_render.page_prepared",
            )

        rendered = render_pdf_to_memory(
            pdf_path,
            dpi=float(pdf_opts.get("dpi", 300.0)),
            pages=pages,
            keep_alpha=bool(pdf_opts.get("alpha", False)),
            target_width=pdf_opts.get("target_width"),
            target_height=pdf_opts.get("target_height"),
            interpolation=str(pdf_opts.get("interpolation", "area")),
            source_bytes=source_bytes,
            on_page_rendered=report_render_progress if self.telemetry is not None else None,
        )

        cache = get_image_cache()
        prefix = str(pdf_opts.get("prefix", "page"))
        fmt = str(pdf_opts.get("format", "png"))

        persist_to_disk = self._should_persist_pdf_images(pdf_opts)

        for page_index, image in rendered:
            stem = f"{prefix}_{page_index + 1:03d}"

            # Cache only if we are NOT persisting to disk (to save memory)
            if not persist_to_disk:
                cache[stem] = image

            # Optionally write to disk for debug/persistence
            if persist_to_disk:
                from src.pdf_to_images import save_image

                destination = output_dir / f"{stem}.{fmt}"
                save_image(destination, image, fmt=fmt)

        return source_sha256, pages

    def _resolve_page_runs(self, page_ids: List[str]) -> List[str]:
        """Resolves which runs to use for each page (legacy manual resolution)."""
        input_runs = get_nested(self.config, "inputs", "runs", default={})
        page_runs = []
        for page_id in page_ids:
            page_runs.append(input_runs.get(page_id, page_id))
        return page_runs

    def _should_persist_pdf_images(self, pdf_opts: Dict[str, Any]) -> bool:
        """Return whether rendered PDF pages must be written to run_dir images."""
        return (
            self.debug
            or self._review_package_config().enabled
            or ("output_dir" not in pdf_opts)
            or (pdf_opts.get("output_dir") is not None)
        )

    def run(self, page_limit: Optional[int] = None) -> Path:
        """Executes the full pipeline."""
        with self._telemetry_stage("input_validation"):
            user_overrides_payload, movement_boundaries = self._validate_input_prerequisites()
        commands: List[List[str]] = []
        pdf_rendered_this_run = False
        rendered_source_sha256: str | None = None
        rendered_source_pages: list[int] | None = None

        if get_nested(self.config, "steps", "pdf_to_images", default=False):
            if (
                self.skip_existing
                and (self.run_dir / "inputs" / "images").exists()
                and list((self.run_dir / "inputs" / "images").glob("*.png"))
            ):
                logger.info("Skipping pdf_to_images: output directory exists and is not empty.")
            else:
                with self._telemetry_stage("pdf_render"):
                    render_provenance = self._run_pdf_to_images()
                commands.append(["inprocess:pdf_to_images"])
                if render_provenance is not None:
                    rendered_source_sha256, rendered_source_pages = render_provenance
                    pdf_rendered_this_run = True

        logger.info("Collecting images...")
        from src.pipeline.utils.images import get_image_cache

        mem_images = get_image_cache()

        # Determine if we skipped disk write during pdf_to_images
        pdf_opts = get_nested(self.config, "inputs", "pdf_to_images", default={}) or {}
        persist_to_disk = self._should_persist_pdf_images(pdf_opts)

        # Only pass in_memory_images to collect_images if we actually used the cache (i.e. did not persist)
        images = collect_images(
            self.config, self.run_dir, in_memory_images=mem_images if not persist_to_disk else None
        )
        if page_limit is not None:
            images = images[:page_limit]
        page_ids = resolve_page_ids(self.config, images)
        source_page_references = resolve_source_page_references(
            self.config,
            images,
            rendered_this_run=pdf_rendered_this_run,
            rendered_source_sha256=rendered_source_sha256,
            rendered_source_pages=rendered_source_pages,
        )
        logger.info(f"Collected {len(images)} images.")

        run_detection = get_nested(self.config, "steps", "detection", default=False)
        probe_output_dir = None
        hybrid_output_dir = None

        if run_detection and not self.validate_only:
            logger.info("Starting detection step...")
            if self.skip_existing:
                if "detection" not in self.config:
                    self.config["detection"] = {}
                self.config["detection"]["probe_skip_existing"] = True

            with self._telemetry_stage(
                "score_detection",
                detail_code="detection.source_generation_and_scoring",
            ):
                det_result = run_detection_step(
                    self.config,
                    images,
                    page_ids,
                    self.run_id,
                    self.run_dir,
                    dry_run=self.dry_run,
                    in_memory_images=mem_images if not persist_to_disk else None,
                )
            commands.extend(det_result["commands"])
            probe_output_dir = det_result["probe_output_dir"]
            hybrid_output_dir = det_result["hybrid_output_dir"]

        excluded_indices = get_user_exclude_indices(self.config)
        excluded_page_ids = {
            page_ids[idx - 1] for idx in excluded_indices if 1 <= idx <= len(page_ids)
        }

        if run_detection and probe_output_dir and hybrid_output_dir:
            resolved = resolve_paths_from_detection(
                self.config, probe_output_dir, hybrid_output_dir, page_ids, images
            )
            page_runs = page_ids
        else:
            page_runs = self._resolve_page_runs(page_ids)
            resolved = resolve_barlines_and_masks_config(
                self.config, page_ids, page_runs, excluded_page_ids=excluded_page_ids
            )

        page_statuses = resolve_page_filters(
            self.config, page_ids, images, resolved, excluded_indices
        )

        for boundary in movement_boundaries["boundaries"]:
            if boundary["page"] >= len(page_ids):
                raise ValueError(
                    "Movement boundary page is outside the ordered pipeline input: "
                    f"{boundary['page']} >= {len(page_ids)}"
                )
        reject_movement_boundaries_on_excluded_pages(
            movement_boundaries,
            {index - 1 for index in excluded_indices if 1 <= index <= len(page_ids)},
        )

        # Phase A: Base Numbering & Barline Correction
        with self._telemetry_stage("measure_construction"):
            res_a = self.run_base_numbering_and_barline_correction(
                page_ids, images, resolved, excluded_page_ids
            )
        page_ctx = res_a["page_ctx"]
        numbering_base_paths = res_a["numbering_base_paths"]
        barline_override_stats = res_a["barline_override_stats"]

        # Phase B: MMR Batch Detection
        mmr_page_ctx = page_ctx
        detector_route = str(
            get_nested(self.config, "detection", "detector_route", default="standard")
        )
        if (
            get_nested(self.config, "steps", "mmr_overrides", default=False)
            and not self.dry_run
            and not self.validate_only
            and detector_route == "dense_full_pipeline"
        ):
            from src.pipeline.mmr_geometry_handoff import build_mmr_page_context

            mmr_page_ctx = build_mmr_page_context(self, page_ids, excluded_page_ids, page_ctx)
        with self._telemetry_stage("measure_number_recognition"):
            self.run_mmr_batch_detection(page_ids, excluded_page_ids, mmr_page_ctx)

        # Phase C: Final Numbering & Overlays
        self._movement_boundaries = movement_boundaries
        with self._telemetry_stage("numbering"):
            numbering_final_paths = self.run_final_numbering_and_overlays(
                page_ids, excluded_page_ids, page_ctx, user_overrides_payload
            )

        with self._telemetry_stage("artifact_materialization"):
            # Post-processing: Combine results
            if len(numbering_base_paths) > 1 and not self.dry_run and not self.validate_only:
                combined_base = {
                    "pages": [
                        page for path in numbering_base_paths for page in load_json(path)["pages"]
                    ]
                }
                write_json(self.intermediate_dir / "numbering_base.json", combined_base)

            if len(numbering_final_paths) > 1 and not self.dry_run and not self.validate_only:
                final_pages = [
                    page for path in numbering_final_paths for page in load_json(path)["pages"]
                ]
                page_metadata = [
                    load_json(path).get("numbering_metadata") for path in numbering_final_paths
                ]
                combined_final = {
                    "pages": final_pages,
                    "numbering_metadata": {
                        "schema_version": FINAL_NUMBERING_SCHEMA_VERSION,
                        "system_index_contract": SYSTEM_INDEX_CONTRACT,
                        "start_number": 1,
                        "next_number": (
                            page_metadata[-1].get("next_number")
                            if isinstance(page_metadata[-1], dict)
                            else None
                        ),
                        "movement_boundaries": movement_boundaries["boundaries"],
                        "pages": page_metadata,
                    },
                }
                write_json(self.outputs_dir / "numbering_final.json", combined_final)

            if not self.dry_run:
                write_json(self.run_dir / "filters.json", {"pages": page_statuses})

                manifest_resolved = self._resolved_for_manifest(
                    page_ids=page_ids,
                    resolved=resolved,
                    page_ctx=page_ctx,
                )
                manifest = build_manifest(
                    self.config,
                    run_id=self.run_id,
                    run_dir=self.run_dir,
                    images=images,
                    page_ids=page_ids,
                    page_runs=page_runs,
                    resolved=manifest_resolved,
                    commands=commands,
                    page_statuses=page_statuses,
                    barline_override_stats=barline_override_stats,
                    source_page_references=source_page_references,
                )
                write_json(self.run_dir / "manifest.json", manifest)
                logger.info(f"Wrote manifest to {self.run_dir / 'manifest.json'}")
                self._materialize_review_package_if_requested(page_ids, excluded_page_ids)

        return self.run_dir

    def _materialize_review_package_if_requested(
        self,
        page_ids: List[str],
        excluded_page_ids: Set[str],
    ) -> Path | None:
        """Materialize the manual-correction review package when enabled."""
        review_config = self._review_package_config()
        if not review_config.enabled:
            return None

        if self.dry_run or self.validate_only:
            logger.info(
                "Skipping manual correction review package materialization for dry-run "
                "or validate-only execution."
            )
            return None

        review_page_ids = [page_id for page_id in page_ids if page_id not in excluded_page_ids]
        if not review_page_ids:
            logger.info(
                "Skipping manual correction review package materialization: no non-excluded pages."
            )
            return None

        materialize_manual_correction_review_package(
            run_root=self.run_dir,
            review_root=review_config.review_root,
            pages=review_page_ids,
            source_pipeline_command=review_config.source_pipeline_command,
            overwrite=review_config.overwrite,
        )
        logger.info(f"Wrote manual correction review package to {review_config.review_root}")
        return review_config.review_root

    def _review_package_config(self) -> _ReviewPackageConfig:
        return resolve_review_package_config(self.config, self.run_dir)

    def _validate_review_package_prerequisites(self) -> None:
        validate_review_package_prerequisites(self.config, self._review_package_config())

    def _resolved_for_manifest(
        self,
        *,
        page_ids: List[str],
        resolved: List[Dict[str, Any]],
        page_ctx: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return resolved_for_manifest(
            review_enabled=self._review_package_config().enabled,
            page_ids=page_ids,
            resolved=resolved,
            page_ctx=page_ctx,
        )

    def _numbering_phase_services(self) -> NumberingPhaseServices:
        """Keep established module-level operation hooks effective for every phase."""
        return NumberingPhaseServices(
            apply_barline_overrides=apply_barline_overrides,
            merge_measure_overrides=merge_measure_overrides,
            normalize_barlines=normalize_barlines,
            empty_numbering_payload=empty_numbering_payload,
            final_numbering_metadata=final_numbering_metadata,
            load_movement_boundary_payload=load_movement_boundary_payload,
            movement_boundaries_for_page=movement_boundaries_for_page,
            persisted_final_next_number=persisted_final_next_number,
            rebase_mmr_overrides_to_page_local=rebase_mmr_overrides_to_page_local,
            reject_movement_boundaries_on_excluded_pages=reject_movement_boundaries_on_excluded_pages,
            run_mmr_batch=run_mmr_batch,
            ensure_dir=ensure_dir,
            load_json=load_json,
            score_to_dict=score_to_dict,
            write_json=write_json,
            tqdm=tqdm,
            torch=torch,
            logger=logger,
        )

    def run_base_numbering_and_barline_correction(
        self,
        page_ids: List[str],
        images: List[Path],
        resolved: List[Dict[str, Any]],
        excluded_page_ids: Set[str],
    ) -> Dict[str, Any]:
        """Phase A: Base Numbering & Barline Correction."""
        return numbering_phases.run_base_numbering_and_barline_correction(
            self,
            page_ids,
            images,
            resolved,
            excluded_page_ids,
            services=self._numbering_phase_services(),
        )

    def run_mmr_batch_detection(
        self,
        page_ids: List[str],
        excluded_page_ids: Set[str],
        page_ctx: Dict[str, Dict[str, Any]],
    ) -> None:
        """Phase B: MMR Batch Detection."""
        return numbering_phases.run_mmr_batch_detection(
            self, page_ids, excluded_page_ids, page_ctx, services=self._numbering_phase_services()
        )

    def run_final_numbering_and_overlays(
        self,
        page_ids: List[str],
        excluded_page_ids: Set[str],
        page_ctx: Dict[str, Dict[str, Any]],
        user_overrides_payload: Optional[Dict[str, Any]],
        movement_boundaries: Optional[Dict[str, Any]] = None,
    ) -> List[Path]:
        """Phase C: Final Numbering & Overlays."""
        return numbering_phases.run_final_numbering_and_overlays(
            self,
            page_ids,
            excluded_page_ids,
            page_ctx,
            user_overrides_payload,
            movement_boundaries,
            services=self._numbering_phase_services(),
        )
