"""Phase B: MMR Batch Detection. Execution only; scheduling stays in orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from src.pipeline.core.config import get_nested

from .phase_services import NumberingPhaseServices


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
