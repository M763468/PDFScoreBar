"""Detection step orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.config import get_nested
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.utils.io import ensure_dir

from .config import get_probe_kwargs
from .hybrid import HybridDetector

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DetectorOrchestrator:
    """Orchestrates hybrid detection, probe scan, and CNN scoring."""

    def __init__(
        self,
        config: Dict[str, Any],
        images: List[Path],
        run_id: str,
        run_dir: Path,
        *,
        dry_run: bool,
        in_memory_images: Dict[str, Any] | None = None,
    ):
        self.config = config
        self.images = images
        self.run_id = run_id
        self.run_dir = run_dir
        self.dry_run = dry_run
        self.in_memory_images = in_memory_images
        self.det_cfg = get_nested(config, "detection", default={}) or {}
        self.skip_existing = bool(self.det_cfg.get("probe_skip_existing", False))
        self.enable_sr = bool(self.det_cfg.get("enable_sr", True))
        self.sr_scale = int(self.det_cfg.get("sr_scale", 2))
        self.commands: List[List[str]] = []
        self.hybrid_output_dir: Path | None = None
        self.probe_output_dir: Path | None = None

    def run_detection(self) -> Dict[str, Any]:
        """Executes the full detection pipeline."""
        hybrid_result = self._run_hybrid_detection()
        self.hybrid_output_dir = hybrid_result["hybrid_output_dir"]
        self.commands.extend(hybrid_result["commands"])

        probe_result = self._run_probe_scan()
        self.probe_output_dir = probe_result["probe_output_dir"]
        self.commands.extend(probe_result["commands"])

        cnn_result = self._run_cnn_scoring()
        self.commands.extend(cnn_result["commands"])

        return {
            "commands": self.commands,
            "hybrid_output_dir": self.hybrid_output_dir,
            "probe_output_dir": self.probe_output_dir,
        }

    def _run_hybrid_detection(self) -> Dict[str, Any]:
        """Step 2.1: Hybrid Detection (Subprocess or In-Process)"""
        detector = HybridDetector(
            det_cfg=self.det_cfg,
            images=self.images,
            run_id=self.run_id,
            project_root=PROJECT_ROOT,
            dry_run=self.dry_run,
            skip_existing=self.skip_existing,
            in_memory_images=self.in_memory_images,
        )
        return detector.run()

    def _run_probe_scan(self) -> Dict[str, Any]:
        """Step 2.2: Probe Scan (Host)"""
        logger.info("--- Step 2.2: Probe Scan (Host) ---")
        probe_output_root = self.run_dir / "intermediate" / "probe_scan"
        ensure_dir(probe_output_root)

        effective_images, effective_sr_scale = self._get_effective_images_for_probe()
        effective_score_name = self._get_effective_score_name()
        resolved_staff_mask_dir = self._resolve_staff_mask_dir()
        resolved_clef_mask_dir = self._resolve_clef_mask_dir()

        if not self.dry_run:
            detect_probe_kwargs = get_probe_kwargs(self.det_cfg)

            # Use verified Golden settings as default if not overridden
            default_filter_kwargs = {
                "left_margin_ratio": 0.25,
                "clef_left_ratio": 0.30,
                "min_height_median_ratio": 0.85,
                "ink_threshold": 180,
                "min_ink_ratio": 0.70,
                "paper_threshold": 200,
                "min_paper_overlap_ratio": 0.6,
                "min_staff_overlap_ratio": 0.15,
                "max_width_ratio": 0.05,
            }
            filter_kwargs = dict(default_filter_kwargs)
            filter_kwargs.update(self.det_cfg.get("candidate_filter_kwargs", {}))

            run_probe_scan_batch(
                images=effective_images,
                output_root=probe_output_root,
                bands_from=self.hybrid_output_dir,
                staff_mask_dir=resolved_staff_mask_dir,
                clef_mask_dir=resolved_clef_mask_dir,
                ink_threshold=int(self.det_cfg.get("ink_threshold", 180)),
                min_ratio=float(self.det_cfg.get("min_ratio", 0.50)),
                min_height_ratio=float(self.det_cfg.get("min_height_ratio", 0.012)),
                min_width_ratio=(
                    float(self.det_cfg.get("min_width_ratio"))
                    if self.det_cfg.get("min_width_ratio") is not None
                    else 0.0001
                ),
                score_name=effective_score_name,
                band_cluster_max_dist=(
                    float(self.det_cfg.get("band_cluster_max_dist"))
                    if self.det_cfg.get("band_cluster_max_dist") is not None
                    else None
                ),
                band_min_row_count=int(self.det_cfg.get("band_min_row_count", 1)),
                vertical_closing=int(self.det_cfg.get("vertical_closing", 4)),
                detect_probe_kwargs=detect_probe_kwargs,
                probe_row_filter_mode=(
                    str(self.det_cfg.get("probe_row_filter_mode"))
                    if self.det_cfg.get("probe_row_filter_mode") is not None
                    else None
                ),
                probe_endpoint_x_scale=(
                    float(self.det_cfg.get("probe_endpoint_x_scale"))
                    if self.det_cfg.get("probe_endpoint_x_scale") is not None
                    else None
                ),
                probe_endpoint_y_scale=(
                    float(self.det_cfg.get("probe_endpoint_y_scale"))
                    if self.det_cfg.get("probe_endpoint_y_scale") is not None
                    else None
                ),
                skip_existing=self.skip_existing,
                input_image_scale=float(effective_sr_scale),
                enable_heuristic_filters=self.det_cfg.get("enable_heuristic_filters", True),
                candidate_filter_kwargs=filter_kwargs,
            )

        # Build command list for logging/return
        cmd_probe = [
            "inprocess:probe_scan",
            "--output-root",
            str(probe_output_root),
            "--bands-from",
            str(self.hybrid_output_dir),
            "--ink-threshold",
            str(self.det_cfg.get("ink_threshold", 230)),
            "--min-ratio",
            str(self.det_cfg.get("min_ratio", 0.70)),
        ]
        if self.skip_existing:
            cmd_probe.append("--skip-existing")

        return {"commands": [cmd_probe], "probe_output_dir": probe_output_root}

    def _run_cnn_scoring(self) -> Dict[str, Any]:
        """Step 2.3: CNN Scoring (Host)"""
        logger.info("--- Step 2.3: CNN Scoring (Host) ---")
        cnn_model = self.det_cfg.get("cnn_model_path")
        if not cnn_model:
            raise ValueError("detection.cnn_model_path is required.")

        if not self.dry_run:
            effective_images, effective_sr_scale = self._get_effective_images_for_probe()
            effective_score_name = self._get_effective_score_name()
            run_cnn_scoring_batch(
                probe_output_root=self.probe_output_dir,
                images=effective_images,
                model_path=Path(cnn_model),
                threshold=float(self.det_cfg.get("cnn_threshold", 0.1)),
                score_name=effective_score_name,
                crop_recenter_on_bbox_ink=bool(
                    self.det_cfg.get("crop_recenter_on_bbox_ink", False)
                ),
                crop_recenter_max_shift_unit_ratio=float(
                    self.det_cfg.get("crop_recenter_max_shift_unit_ratio", 0.35)
                ),
                input_image_scale=float(effective_sr_scale),
                bands_from=self.hybrid_output_dir,
                staff_vov_threshold=float(self.det_cfg.get("staff_vov_threshold", 0.5)),
                in_memory_images=self.in_memory_images,
            )
        cmd_score = [
            "inprocess:cnn_scoring",
            "--model",
            str(cnn_model),
            "--logs",
            str(self.probe_output_dir),
            "--threshold",
            str(self.det_cfg.get("cnn_threshold", 0.1)),
        ]
        return {"commands": [cmd_score]}

    def _get_effective_images_for_probe(self) -> tuple[List[Path], int]:
        """Returns images and scale to use for probe scan (SR or original)."""
        if self.enable_sr:
            effective_images = []
            for img in self.images:
                sr_img_path = self.hybrid_output_dir / "sr" / "batch" / img.stem / f"{img.stem}.png"
                if sr_img_path.exists():
                    effective_images.append(sr_img_path)
                else:
                    logger.warning("SR image not found for %s, using original.", img.stem)
                    effective_images.append(img)
            return effective_images, self.sr_scale
        return self.images, 1

    def _get_effective_score_name(self) -> str | None:
        """Derive score name from config, or None to let it be per-image."""
        return self.det_cfg.get("probe_score_name")

    def _resolve_staff_mask_dir(self) -> Path | None:
        """Resolves where to look for staff masks."""
        override = self.det_cfg.get("staff_mask_dir", "DEFAULT_SENTINEL")
        if override == "DEFAULT_SENTINEL":
            return self.hybrid_output_dir
        return Path(override) if override is not None else None

    def _resolve_clef_mask_dir(self) -> Path | None:
        """Resolves where to look for clef masks."""
        override = self.det_cfg.get("clef_mask_dir", "DEFAULT_SENTINEL")
        if override == "DEFAULT_SENTINEL":
            return self.hybrid_output_dir
        return Path(override) if override is not None else None


def run_detection_step(
    config: Dict[str, Any],
    images: List[Path],
    page_ids: List[str],
    run_id: str,
    run_dir: Path,
    *,
    dry_run: bool,
    in_memory_images: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run hybrid detection -> probe scan -> CNN scoring using DetectorOrchestrator."""
    orchestrator = DetectorOrchestrator(
        config=config,
        images=images,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )
    return orchestrator.run_detection()
