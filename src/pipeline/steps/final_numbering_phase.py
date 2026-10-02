"""Phase C: Final Numbering & Overlays. Execution only; scheduling stays in orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.pipeline.core.config import get_nested

from .phase_services import NumberingPhaseServices


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
