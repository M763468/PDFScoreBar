"""Phase A: Base Numbering & Barline Correction. Execution only; scheduling stays in orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from src.common.barline_geometry import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
)
from src.pipeline.core.config import get_nested

from .phase_services import NumberingPhaseServices


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
