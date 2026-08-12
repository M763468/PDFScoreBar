"""Pipeline orchestration for end-to-end processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import torch
from tqdm import tqdm

from src.common.barline_evaluation import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
)
from src.pdf_to_images import normalise_pages
from src.pipeline.core.config import get_nested
from src.pipeline.core.manifest import build_manifest
from src.pipeline.detection import (
    resolve_barlines_and_masks_config,
    resolve_paths_from_detection,
    run_detection_step,
)
from src.pipeline.review.manual_correction_materializer import (
    materialize_manual_correction_review_package,
)
from src.pipeline.steps.barlines import (
    apply_barline_overrides,
    merge_measure_overrides,
    normalize_barlines,
)
from src.pipeline.steps.filters import get_user_exclude_indices, resolve_page_filters
from src.pipeline.steps.numbering import (
    empty_numbering_payload,
    rebase_mmr_overrides_to_page_local,
    run_mmr_batch,
)
from src.pipeline.utils.images import collect_images, resolve_page_ids
from src.pipeline.utils.io import ensure_dir, load_json, score_to_dict, write_json

logger = logging.getLogger(__name__)

# Persistence: Cache HomrPredictor and other heavy models to avoid re-loading.
_PIPELINE_PERSISTENCE: Dict[str, Any] = {}
# MMR Persistence: Cache MMRClassifier and MMROCREngine to avoid re-loading models.
_MMR_PERSISTENCE: Dict[Any, Any] = {}


@dataclass(frozen=True)
class _ReviewPackageConfig:
    enabled: bool
    review_root: Path
    overwrite: bool
    source_pipeline_command: str | None


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
    ):
        self.config = config
        self.run_id = run_id
        self.run_dir = run_dir
        self.dry_run = dry_run
        self.validate_only = validate_only
        self.skip_existing = skip_existing
        self.debug = debug

        self.intermediate_dir = run_dir / "intermediate"
        self.outputs_dir = run_dir / "outputs"

        # Persistence: Link to module-level cache
        self._persistence = _PIPELINE_PERSISTENCE
        self._mmr_persistence = _MMR_PERSISTENCE

    def _run_pdf_to_images(self) -> None:
        """Step 1: Convert PDF to images in-process."""
        pdf_path = get_nested(self.config, "inputs", "pdf_path")
        pdf_opts = get_nested(self.config, "inputs", "pdf_to_images", default={}) or {}
        if not pdf_path:
            raise ValueError("inputs.pdf_path is required when pdf_to_images is enabled.")

        output_dir = self.run_dir / "inputs" / "images"
        ensure_dir(output_dir)

        if self.dry_run:
            logger.info(f"Executing (dry-run): render_pdf {pdf_path} -> {output_dir}")
            return

        import fitz

        pdf_path = Path(pdf_path)
        with fitz.open(pdf_path) as doc:
            pages = normalise_pages(pdf_opts.get("pages"), doc.page_count)

        logger.info(f"Rendering PDF: {pdf_path} (pages: {pages}) -> {output_dir}")
        from src.pdf_to_images import render_pdf_to_memory
        from src.pipeline.utils.images import get_image_cache

        rendered = render_pdf_to_memory(
            pdf_path,
            dpi=float(pdf_opts.get("dpi", 300.0)),
            pages=pages,
            keep_alpha=bool(pdf_opts.get("alpha", False)),
            target_width=pdf_opts.get("target_width"),
            target_height=pdf_opts.get("target_height"),
            interpolation=str(pdf_opts.get("interpolation", "area")),
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
        self._validate_review_package_prerequisites()
        commands: List[List[str]] = []

        if get_nested(self.config, "steps", "pdf_to_images", default=False):
            if (
                self.skip_existing
                and (self.run_dir / "inputs" / "images").exists()
                and list((self.run_dir / "inputs" / "images").glob("*.png"))
            ):
                logger.info("Skipping pdf_to_images: output directory exists and is not empty.")
            else:
                self._run_pdf_to_images()
                commands.append(["inprocess:pdf_to_images"])

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

        user_overrides_path = get_nested(self.config, "inputs", "measure_overrides")
        user_overrides_payload = None
        if user_overrides_path:
            user_overrides_payload = load_json(Path(user_overrides_path))

        # Phase A: Base Numbering & Barline Correction
        res_a = self.run_base_numbering_and_barline_correction(
            page_ids, images, resolved, excluded_page_ids
        )
        page_ctx = res_a["page_ctx"]
        numbering_base_paths = res_a["numbering_base_paths"]
        barline_override_stats = res_a["barline_override_stats"]

        # Phase B: MMR Batch Detection
        self.run_mmr_batch_detection(page_ids, excluded_page_ids, page_ctx)

        # Phase C: Final Numbering & Overlays
        numbering_final_paths = self.run_final_numbering_and_overlays(
            page_ids, excluded_page_ids, page_ctx, user_overrides_payload
        )

        # Post-processing: Combine results
        if len(numbering_base_paths) > 1 and not self.dry_run and not self.validate_only:
            combined_base = {
                "pages": [
                    page for path in numbering_base_paths for page in load_json(path)["pages"]
                ]
            }
            write_json(self.intermediate_dir / "numbering_base.json", combined_base)

        if len(numbering_final_paths) > 1 and not self.dry_run and not self.validate_only:
            combined_final = {
                "pages": [
                    page for path in numbering_final_paths for page in load_json(path)["pages"]
                ]
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
        """Resolve the config-first review package output contract.

        This is intentionally scoped to the low-level ``run_pipeline()`` layout.
        The #226/#227 public ``OUTPUT_DIR/{final,review,debug}`` materializer is
        a separate follow-up surface.
        """
        review_cfg = get_nested(self.config, "outputs", "review", default={}) or {}
        if not isinstance(review_cfg, dict):
            raise ValueError("outputs.review must be a mapping when provided.")

        enabled = bool(review_cfg.get("manual_correction_package", False))
        review_root_raw = review_cfg.get("root")
        if review_root_raw:
            review_root = Path(str(review_root_raw))
            if not review_root.is_absolute():
                review_root = self.run_dir / review_root
        else:
            review_root = self.run_dir / "review"

        source_pipeline_command_raw = review_cfg.get("source_pipeline_command")
        source_pipeline_command = (
            str(source_pipeline_command_raw) if source_pipeline_command_raw else None
        )

        return _ReviewPackageConfig(
            enabled=enabled,
            review_root=review_root,
            overwrite=review_cfg.get("overwrite") is not False,
            source_pipeline_command=source_pipeline_command,
        )

    def _validate_review_package_prerequisites(self) -> None:
        review_config = self._review_package_config()
        if not review_config.enabled:
            return

        required_steps = {
            "numbering_base": get_nested(self.config, "steps", "numbering_base", default=False),
            "mmr_overrides": get_nested(self.config, "steps", "mmr_overrides", default=False),
            "overlay": get_nested(self.config, "steps", "overlay", default=False),
        }
        missing = [name for name, enabled in required_steps.items() if not enabled]
        if missing:
            raise ValueError(
                "outputs.review.manual_correction_package requires these steps to be enabled: "
                + ", ".join(missing)
            )

    def _resolved_for_manifest(
        self,
        *,
        page_ids: List[str],
        resolved: List[Dict[str, Any]],
        page_ctx: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        manifest_resolved = []
        review_enabled = self._review_package_config().enabled
        for page_id, item in zip(page_ids, resolved):
            manifest_item = dict(item)
            corrected_path = page_ctx.get(page_id, {}).get("barlines_path")
            if review_enabled and corrected_path and Path(corrected_path).exists():
                manifest_item["barlines_json"] = str(corrected_path)
            manifest_resolved.append(manifest_item)
        return manifest_resolved

    def run_base_numbering_and_barline_correction(
        self,
        page_ids: List[str],
        images: List[Path],
        resolved: List[Dict[str, Any]],
        excluded_page_ids: Set[str],
    ) -> Dict[str, Any]:
        """Phase A: Base Numbering & Barline Correction."""
        from src.measure_numbering.pipeline import MeasureNumberingPipeline

        if "numbering_pipeline" not in self._persistence:
            self._persistence["numbering_pipeline"] = MeasureNumberingPipeline()
        numbering_pipeline = self._persistence["numbering_pipeline"]

        numbering_base_paths: List[Path] = []
        barline_override_stats: Dict[str, Dict[str, int]] = {}
        page_ctx: Dict[str, Dict[str, Any]] = {}

        apply_barlines = get_nested(self.config, "steps", "apply_barline_overrides", default=False)
        barline_overrides_path = get_nested(self.config, "inputs", "barline_overrides")
        barline_override_payload = None
        if barline_overrides_path:
            barline_override_payload = load_json(Path(barline_overrides_path))

        barline_override_cfg = (
            get_nested(self.config, "inputs", "barline_overrides_config", default={}) or {}
        )
        barline_iou_threshold = float(barline_override_cfg.get("iou_threshold", 0.5))
        barline_min_width = int(barline_override_cfg.get("min_width", BARLINE_DEFAULT_MIN_WIDTH))
        barline_x_margin = int(barline_override_cfg.get("x_margin", BARLINE_X_MARGIN))
        barline_y_margin = int(barline_override_cfg.get("y_margin", BARLINE_Y_MARGIN))

        step_numbering = get_nested(self.config, "steps", "numbering_base", default=False)
        force_single_system = bool(
            get_nested(self.config, "numbering", "force_single_system", default=False)
        )

        for index, (page_id, image_path, resolved_item) in tqdm(
            enumerate(zip(page_ids, images, resolved), start=1),
            total=len(page_ids),
            desc="Phase A: Base Numbering",
            unit="page",
        ):
            page_intermediate = self.intermediate_dir / page_id
            page_outputs = self.outputs_dir / page_id
            ensure_dir(page_intermediate)
            ensure_dir(page_outputs)

            page_ctx[page_id] = {
                "index": index,
                "image_path": image_path,
                "resolved": resolved_item,
                "intermediate_dir": page_intermediate,
                "outputs_dir": page_outputs,
            }

            if page_id in excluded_page_ids:
                empty_base = page_intermediate / "numbering_base.json"
                numbering_base_paths.append(empty_base)
                page_ctx[page_id]["numbering_base"] = empty_base
                if not self.dry_run:
                    write_json(empty_base, empty_numbering_payload(index, image_path))
                barline_override_stats[page_id] = {
                    "removed": 0,
                    "added": 0,
                    "remove_requests": 0,
                    "unmatched_remove": 0,
                }
                continue

            # 1. Barline Correction
            barlines_path = Path(resolved_item["barlines_json"])
            if apply_barlines:
                corrected_path = page_intermediate / "barlines_corrected.json"
                if barline_override_payload and isinstance(
                    barline_override_payload.get("barline_overrides", []), list
                ):
                    raw_barlines = load_json(barlines_path)
                    barlines_list = normalize_barlines(raw_barlines)
                    corrected, stats = apply_barline_overrides(
                        barlines_list,
                        barline_override_payload.get("barline_overrides", []),
                        page_index=index - 1,
                        iou_threshold=barline_iou_threshold,
                        min_width=barline_min_width,
                        x_margin=barline_x_margin,
                        y_margin=barline_y_margin,
                    )
                    barline_override_stats[page_id] = stats
                    if not self.dry_run and (self.debug or self._review_package_config().enabled):
                        write_json(corrected_path, corrected)
                    page_ctx[page_id]["corrected_barlines"] = corrected
                else:
                    if not self.dry_run and self.debug and barlines_path.exists():
                        corrected_path.write_text(barlines_path.read_text())
                    if barlines_path.exists():
                        page_ctx[page_id]["corrected_barlines"] = load_json(barlines_path)
                    barline_override_stats[page_id] = {
                        "removed": 0,
                        "added": 0,
                        "remove_requests": 0,
                        "unmatched_remove": 0,
                    }
                barlines_path = corrected_path
            else:
                barline_override_stats[page_id] = {
                    "removed": 0,
                    "added": 0,
                    "remove_requests": 0,
                    "unmatched_remove": 0,
                }
            page_ctx[page_id]["barlines_path"] = barlines_path

            # 2. Base Numbering
            numbering_base = page_intermediate / "numbering_base.json"
            numbering_base_paths.append(numbering_base)
            page_ctx[page_id]["numbering_base"] = numbering_base

            if step_numbering and not self.validate_only:
                if self.skip_existing and numbering_base.exists():
                    logger.info(f"Skipping numbering_base for {page_id}: file exists.")
                else:
                    if not self.dry_run:
                        if "corrected_barlines" in page_ctx[page_id]:
                            barline_boxes = page_ctx[page_id]["corrected_barlines"]
                        else:
                            raw_barlines = load_json(Path(resolved_item["barlines_json"]))
                            barline_boxes = normalize_barlines(raw_barlines)

                        from src.pipeline.utils.images import load_image

                        img_ref = load_image(image_path)
                        h, w = img_ref.shape[:2]

                        page_obj = numbering_pipeline.process_page(
                            barline_boxes,
                            Path(resolved_item["staff_mask"]),
                            (w, h),
                            page_number=index,
                            assume_one_staff_per_system=force_single_system,
                            image=img_ref,
                        )
                        from src.measure_numbering.types import Score

                        temp_score = Score()
                        temp_score.pages.append(page_obj)
                        numbering_pipeline.numberer.number_score(temp_score, start_number=1)
                        write_json(numbering_base, score_to_dict(temp_score))

        return {
            "page_ctx": page_ctx,
            "numbering_base_paths": numbering_base_paths,
            "barline_override_stats": barline_override_stats,
        }

    def run_mmr_batch_detection(
        self,
        page_ids: List[str],
        excluded_page_ids: Set[str],
        page_ctx: Dict[str, Dict[str, Any]],
    ) -> None:
        """Phase B: MMR Batch Detection."""
        step_mmr = get_nested(self.config, "steps", "mmr_overrides", default=False)
        if not step_mmr or self.validate_only:
            return

        enable_rotation_tta = bool(
            get_nested(self.config, "mmr", "enable_rotation_tta", default=False)
        )
        model_path = get_nested(self.config, "mmr", "model_path")
        model_path = Path(model_path) if model_path else None
        debug_root = get_nested(self.config, "mmr", "debug_root")
        debug_root = Path(debug_root) if debug_root else None

        mmr_input_pages = []
        mmr_input_images = []
        mmr_output_paths = []

        for page_id in page_ids:
            if page_id in excluded_page_ids:
                continue
            ctx = page_ctx[page_id]
            numbering_base = ctx["numbering_base"]
            overrides_mmr = ctx["intermediate_dir"] / "overrides_mmr.json"

            if self.skip_existing and overrides_mmr.exists():
                logger.info(f"Skipping MMR preparation for {page_id}: file exists.")
                continue

            if not self.dry_run and numbering_base.exists():
                mmr_input_pages.append(load_json(numbering_base))
                mmr_input_images.append(ctx["image_path"])
                mmr_output_paths.append(overrides_mmr)
            else:
                logger.warning(f"MMR skipped for {page_id} because numbering_base.json is missing.")

        if mmr_input_pages:
            logger.info(f"Running MMR batch for {len(mmr_input_pages)} pages...")
            if not model_path:
                raise ValueError("mmr.model_path is required for MMR step.")

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            from src.measure_numbering.mmr import MMRClassifier, MMROCREngine

            classifier_key = ("classifier", str(model_path), str(device))
            if classifier_key not in self._mmr_persistence:
                logger.info(
                    f"Initializing persistent MMRClassifier with model: {model_path} on {device}"
                )
                self._mmr_persistence[classifier_key] = MMRClassifier(model_path, device)

            ocr_key = ("ocr_engine", enable_rotation_tta)
            if ocr_key not in self._mmr_persistence:
                logger.info(
                    f"Initializing persistent MMROCREngine (RapidOCR) with rotation_tta={enable_rotation_tta}"
                )
                self._mmr_persistence[ocr_key] = MMROCREngine(
                    enable_rotation_tta=enable_rotation_tta
                )

            run_mmr_batch(
                pages_data=mmr_input_pages,
                image_paths=mmr_input_images,
                output_paths=mmr_output_paths,
                model_path=model_path,
                device=device,
                enable_rotation_tta=enable_rotation_tta,
                debug_root=debug_root,
                classifier=self._mmr_persistence[classifier_key],
                ocr_engine=self._mmr_persistence[ocr_key],
            )
            if device.type == "cuda":
                torch.cuda.empty_cache()
        else:
            logger.info("No pages to process for MMR batch.")

    def run_final_numbering_and_overlays(
        self,
        page_ids: List[str],
        excluded_page_ids: Set[str],
        page_ctx: Dict[str, Dict[str, Any]],
        user_overrides_payload: Optional[Dict[str, Any]],
    ) -> List[Path]:
        """Phase C: Final Numbering & Overlays."""
        step_mmr = get_nested(self.config, "steps", "mmr_overrides", default=False)
        step_apply = get_nested(self.config, "steps", "apply_measure_overrides", default=False)
        step_overlay = get_nested(self.config, "steps", "overlay", default=False)
        apply_barlines = get_nested(self.config, "steps", "apply_barline_overrides", default=False)
        force_single_system = bool(
            get_nested(self.config, "numbering", "force_single_system", default=False)
        )

        numbering_final_paths: List[Path] = []
        numbering_pipeline = self._persistence.get("numbering_pipeline")
        if numbering_pipeline is None:
            from src.measure_numbering.pipeline import MeasureNumberingPipeline

            numbering_pipeline = MeasureNumberingPipeline()
            self._persistence["numbering_pipeline"] = numbering_pipeline

        for page_id in tqdm(page_ids, desc="Phase C: Final Numbering", unit="page"):
            ctx = page_ctx[page_id]
            page_intermediate = ctx["intermediate_dir"]
            page_outputs = ctx["outputs_dir"]
            index = ctx["index"]
            image_path = ctx["image_path"]
            resolved_item = ctx["resolved"]

            if page_id in excluded_page_ids:
                if (step_apply or step_overlay) and not self.validate_only:
                    empty_final = page_outputs / "numbering_final.json"
                    numbering_final_paths.append(empty_final)
                    if not self.dry_run:
                        write_json(empty_final, empty_numbering_payload(index, image_path))
                continue

            mmr_overrides_payload = None
            if step_mmr and not self.validate_only:
                overrides_mmr = page_intermediate / "overrides_mmr.json"
                if not self.dry_run and overrides_mmr.exists():
                    mmr_overrides_payload = rebase_mmr_overrides_to_page_local(
                        load_json(overrides_mmr)
                    )

            if (step_apply or step_overlay) and not self.validate_only:
                overrides_payload = merge_measure_overrides(
                    mmr_overrides_payload, user_overrides_payload
                )
                if not self.dry_run and self.debug:
                    write_json(page_intermediate / "overrides_combined.json", overrides_payload)

                final_json = page_outputs / "numbering_final.json"
                numbering_final_paths.append(final_json)
                overlay_path = page_outputs / "numbering_overlay.png" if step_overlay else None

                if (
                    self.skip_existing
                    and final_json.exists()
                    and (not overlay_path or overlay_path.exists())
                ):
                    logger.info(f"Skipping final_numbering for {page_id}: file exists.")
                else:
                    if not self.dry_run:
                        raw_barlines = load_json(Path(resolved_item["barlines_json"]))
                        barline_boxes = normalize_barlines(raw_barlines)
                        if apply_barlines:
                            if "corrected_barlines" in ctx:
                                barline_boxes = ctx["corrected_barlines"]
                            elif ctx["barlines_path"].exists():
                                barline_boxes = normalize_barlines(load_json(ctx["barlines_path"]))

                        from src.pipeline.utils.images import load_image

                        img_ref = load_image(image_path)
                        h, w = img_ref.shape[:2]

                        page_obj = numbering_pipeline.process_page(
                            barline_boxes,
                            Path(resolved_item["staff_mask"]),
                            (w, h),
                            page_number=index,
                            assume_one_staff_per_system=force_single_system,
                            image=img_ref,
                        )
                        from src.measure_numbering.types import Score

                        temp_score = Score()
                        temp_score.pages.append(page_obj)

                        ov = overrides_payload.get("measure_overrides")
                        numbering_pipeline.numberer.number_score(
                            temp_score, start_number=1, overrides=ov
                        )
                        write_json(final_json, score_to_dict(temp_score))

                        if step_overlay and overlay_path:
                            from tools.add_measure_numbers import render_overlay

                            render_overlay(temp_score, image_path, overlay_path)

        return numbering_final_paths
