"""Numbering phase execution and services; scheduling remains in the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from src.common.barline_geometry import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
)
from src.pipeline.core import get_nested


@dataclass(frozen=True)
class NumberingPhaseServices:
    apply_barline_overrides: Callable[..., Any]
    merge_measure_overrides: Callable[..., Any]
    normalize_barlines: Callable[..., Any]
    empty_numbering_payload: Callable[..., Any]
    final_numbering_metadata: Callable[..., Any]
    load_movement_boundary_payload: Callable[..., Any]
    movement_boundaries_for_page: Callable[..., Any]
    persisted_final_next_number: Callable[..., Any]
    rebase_mmr_overrides_to_page_local: Callable[..., Any]
    reject_movement_boundaries_on_excluded_pages: Callable[..., Any]
    run_mmr_batch: Callable[..., Any]
    ensure_dir: Callable[..., Any]
    load_json: Callable[..., Any]
    score_to_dict: Callable[..., Any]
    write_json: Callable[..., Any]
    tqdm: Callable[..., Any]
    torch: Any
    logger: Any


def run_base_numbering_and_barline_correction(
    self,
    page_ids: List[str],
    images: List[Path],
    resolved: List[Dict[str, Any]],
    excluded_page_ids: Set[str],
    *,
    services: NumberingPhaseServices,
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
    barline_override_payload = self._barline_override_payload

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

    for index, (page_id, image_path, resolved_item) in services.tqdm(
        enumerate(zip(page_ids, images, resolved), start=1),
        total=len(page_ids),
        desc="Phase A: Base Numbering",
        unit="page",
    ):
        page_intermediate = self.intermediate_dir / page_id
        page_outputs = self.outputs_dir / page_id
        services.ensure_dir(page_intermediate)
        services.ensure_dir(page_outputs)

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
                services.write_json(empty_base, services.empty_numbering_payload(index, image_path))
            barline_override_stats[page_id] = {
                "removed": 0,
                "added": 0,
                "remove_requests": 0,
                "unmatched_remove": 0,
            }
            self._telemetry_progress(
                "measure_construction",
                page_number=index,
                completed_units=index,
                total_units=len(page_ids),
                unit="page",
                detail_code="page_skipped.user_excluded",
            )
            continue

        # 1. Barline Correction
        barlines_path = Path(resolved_item["barlines_json"])
        corrected_path = page_intermediate / "barlines_corrected.json"
        if apply_barlines:
            if barline_override_payload and isinstance(
                barline_override_payload.get("barline_overrides", []), list
            ):
                raw_barlines = services.load_json(barlines_path)
                barlines_list = services.normalize_barlines(raw_barlines)
                corrected, stats = services.apply_barline_overrides(
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
                    services.write_json(corrected_path, corrected)
                page_ctx[page_id]["corrected_barlines"] = corrected
            else:
                if not self.dry_run and self.debug and barlines_path.exists():
                    corrected_path.write_text(barlines_path.read_text())
                if barlines_path.exists():
                    page_ctx[page_id]["corrected_barlines"] = services.load_json(barlines_path)
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
            if (
                self._review_package_config().enabled
                and not self.dry_run
                and barlines_path.exists()
            ):
                corrected_path.write_text(
                    barlines_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                barlines_path = corrected_path
        page_ctx[page_id]["barlines_path"] = barlines_path

        # 2. Base Numbering
        numbering_base = page_intermediate / "numbering_base.json"
        numbering_base_paths.append(numbering_base)
        page_ctx[page_id]["numbering_base"] = numbering_base

        if step_numbering and not self.validate_only:
            if self.skip_existing and numbering_base.exists():
                services.logger.info(f"Skipping numbering_base for {page_id}: file exists.")
            else:
                if not self.dry_run:
                    if "corrected_barlines" in page_ctx[page_id]:
                        barline_boxes = page_ctx[page_id]["corrected_barlines"]
                    else:
                        raw_barlines = services.load_json(Path(resolved_item["barlines_json"]))
                        barline_boxes = services.normalize_barlines(raw_barlines)

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
                    services.write_json(numbering_base, services.score_to_dict(temp_score))

        self._telemetry_progress(
            "measure_construction",
            page_number=index,
            completed_units=index,
            total_units=len(page_ids),
            unit="page",
            detail_code="measure_construction.page_completed",
        )

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
    *,
    services: NumberingPhaseServices,
) -> None:
    """Phase B: MMR Batch Detection."""
    step_mmr = get_nested(self.config, "steps", "mmr_overrides", default=False)
    if not step_mmr or self.validate_only:
        return

    enable_rotation_tta = bool(get_nested(self.config, "mmr", "enable_rotation_tta", default=False))
    model_path = get_nested(self.config, "mmr", "model_path")
    model_path = Path(model_path) if model_path else None
    debug_root = get_nested(self.config, "mmr", "debug_root")
    debug_root = Path(debug_root) if debug_root else None

    mmr_input_pages = []
    mmr_input_images = []
    mmr_output_paths = []
    mmr_input_page_numbers = []
    mmr_support_data = []

    for page_id in page_ids:
        if page_id in excluded_page_ids:
            continue
        ctx = page_ctx[page_id]
        numbering_base = ctx["numbering_base"]
        overrides_mmr = ctx["intermediate_dir"] / "overrides_mmr.json"

        if self.skip_existing and overrides_mmr.exists():
            services.logger.info(f"Skipping MMR preparation for {page_id}: file exists.")
            continue

        if not self.dry_run and numbering_base.exists():
            mmr_input_pages.append(services.load_json(numbering_base))
            mmr_input_images.append(ctx["image_path"])
            mmr_output_paths.append(overrides_mmr)
            mmr_input_page_numbers.append(ctx["index"])
            support_path = ctx.get("mmr_support")
            mmr_support_data.append(services.load_json(support_path) if support_path else None)
        else:
            services.logger.warning(
                f"MMR skipped for {page_id} because numbering_base.json is missing."
            )
            self._telemetry_progress(
                "measure_number_recognition",
                page_number=ctx["index"],
                detail_code="mmr.skipped_missing_numbering_base",
            )

    if mmr_input_pages:
        services.logger.info(f"Running MMR batch for {len(mmr_input_pages)} pages...")
        if not model_path:
            raise ValueError("mmr.model_path is required for MMR step.")

        device = services.torch.device("cuda" if services.torch.cuda.is_available() else "cpu")
        from src.measure_numbering.mmr import MMRClassifier, MMROCREngine

        classifier_key = ("classifier", str(model_path), str(device))
        if classifier_key not in self._mmr_persistence:
            services.logger.info(
                f"Initializing persistent MMRClassifier with model: {model_path} on {device}"
            )
            self._mmr_persistence[classifier_key] = MMRClassifier(model_path, device)

        ocr_key = ("ocr_engine", enable_rotation_tta)
        if ocr_key not in self._mmr_persistence:
            services.logger.info(
                f"Initializing persistent MMROCREngine (RapidOCR) with rotation_tta={enable_rotation_tta}"
            )
            self._mmr_persistence[ocr_key] = MMROCREngine(enable_rotation_tta=enable_rotation_tta)

        services.run_mmr_batch(
            pages_data=mmr_input_pages,
            image_paths=mmr_input_images,
            output_paths=mmr_output_paths,
            model_path=model_path,
            device=device,
            enable_rotation_tta=enable_rotation_tta,
            debug_root=debug_root,
            classifier=self._mmr_persistence[classifier_key],
            ocr_engine=self._mmr_persistence[ocr_key],
            support_data=mmr_support_data,
        )
        if device.type == "cuda":
            services.torch.cuda.empty_cache()
        for completed, page_number in enumerate(mmr_input_page_numbers, start=1):
            self._telemetry_progress(
                "measure_number_recognition",
                page_number=page_number,
                completed_units=completed,
                total_units=len(mmr_input_page_numbers),
                unit="page",
                detail_code="mmr.page_completed",
            )
    else:
        services.logger.info("No pages to process for MMR batch.")


def run_final_numbering_and_overlays(
    self,
    page_ids: List[str],
    excluded_page_ids: Set[str],
    page_ctx: Dict[str, Dict[str, Any]],
    user_overrides_payload: Optional[Dict[str, Any]],
    movement_boundaries: Optional[Dict[str, Any]] = None,
    *,
    services: NumberingPhaseServices,
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

    movement_boundaries = movement_boundaries or self._movement_boundaries
    movement_boundaries = movement_boundaries or services.load_movement_boundary_payload(None)
    services.reject_movement_boundaries_on_excluded_pages(
        movement_boundaries,
        {page_ctx[page_id]["index"] - 1 for page_id in excluded_page_ids if page_id in page_ctx},
    )
    current_number = 1

    for page_id in services.tqdm(page_ids, desc="Phase C: Final Numbering", unit="page"):
        ctx = page_ctx[page_id]
        page_intermediate = ctx["intermediate_dir"]
        page_outputs = ctx["outputs_dir"]
        index = ctx["index"]
        image_path = ctx["image_path"]
        resolved_item = ctx["resolved"]
        page_boundaries = services.movement_boundaries_for_page(movement_boundaries, index - 1)
        page_start_number = current_number

        if page_id in excluded_page_ids:
            if (step_apply or step_overlay) and not self.validate_only:
                empty_final = page_outputs / "numbering_final.json"
                numbering_final_paths.append(empty_final)
                if not self.dry_run:
                    empty_payload = services.empty_numbering_payload(index, image_path)
                    empty_payload["numbering_metadata"] = services.final_numbering_metadata(
                        page_index=index - 1,
                        start_number=page_start_number,
                        next_number=current_number,
                        boundaries=page_boundaries,
                    )
                    services.write_json(empty_final, empty_payload)
            self._telemetry_progress(
                "numbering",
                page_number=index,
                completed_units=index,
                total_units=len(page_ids),
                unit="page",
                detail_code="page_skipped.user_excluded",
            )
            continue

        mmr_overrides_payload = None
        if step_mmr and not self.validate_only:
            overrides_mmr = page_intermediate / "overrides_mmr.json"
            if not self.dry_run and overrides_mmr.exists():
                mmr_overrides_payload = services.load_json(overrides_mmr)

        if (step_apply or step_overlay) and not self.validate_only:
            overrides_payload = services.merge_measure_overrides(
                mmr_overrides_payload, user_overrides_payload
            )
            if overrides_payload is not None:
                overrides_payload = services.rebase_mmr_overrides_to_page_local(
                    overrides_payload,
                    page_index=index - 1,
                )
            if not self.dry_run and self.debug:
                services.write_json(
                    page_intermediate / "overrides_combined.json", overrides_payload
                )

            final_json = page_outputs / "numbering_final.json"
            numbering_final_paths.append(final_json)
            overlay_path = page_outputs / "numbering_overlay.png" if step_overlay else None

            persisted_next_number = None
            if self.skip_existing and final_json.exists():
                persisted_next_number = services.persisted_final_next_number(
                    final_json,
                    expected_start_number=current_number,
                    expected_boundaries=page_boundaries,
                )
            can_skip_existing = (
                self.skip_existing
                and final_json.exists()
                and (not overlay_path or overlay_path.exists())
                and persisted_next_number is not None
            )
            if can_skip_existing:
                services.logger.info(f"Skipping final_numbering for {page_id}: file exists.")
                current_number = persisted_next_number
            else:
                if not self.dry_run:
                    raw_barlines = services.load_json(Path(resolved_item["barlines_json"]))
                    barline_boxes = services.normalize_barlines(raw_barlines)
                    if apply_barlines:
                        if "corrected_barlines" in ctx:
                            barline_boxes = ctx["corrected_barlines"]
                        elif ctx["barlines_path"].exists():
                            barline_boxes = services.normalize_barlines(
                                services.load_json(ctx["barlines_path"])
                            )

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
                    local_boundary_resets = {
                        (0, boundary["system"]): boundary["reset_number"]
                        for boundary in page_boundaries
                    }
                    next_number = numbering_pipeline.numberer.number_score(
                        temp_score,
                        start_number=current_number,
                        overrides=ov,
                        boundary_resets=local_boundary_resets,
                    )
                    final_payload = services.score_to_dict(temp_score)
                    final_payload["numbering_metadata"] = services.final_numbering_metadata(
                        page_index=index - 1,
                        start_number=current_number,
                        next_number=next_number,
                        boundaries=page_boundaries,
                    )
                    services.write_json(final_json, final_payload)
                    current_number = next_number

                    if step_overlay and overlay_path:
                        from src.measure_numbering.cli import render_overlay

                        render_overlay(temp_score, image_path, overlay_path)

        self._telemetry_progress(
            "numbering",
            page_number=index,
            completed_units=index,
            total_units=len(page_ids),
            unit="page",
            detail_code="numbering.page_completed",
        )

    return numbering_final_paths
