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
        """Runs the complete detection step (Hybrid + Probe + CNN)."""
        # --- Pass 1: Hybrid + Seed Generation (Optional) ---
        seed_gen_cfg = self.det_cfg.get("seed_generation")
        if seed_gen_cfg:
            # We must run a specific hybrid consensus (Union Baseline+SR, and OMR if enabled)
            # to match v12 clean seed generation sources.
            hybrid_result = self._run_hybrid_detection(use_omr=bool(self.det_cfg.get("use_omr", False)))
            self.hybrid_output_dir = hybrid_result["hybrid_output_dir"]
        else:
            # Standard single-pass behavior
            hybrid_result = self._run_hybrid_detection(use_omr=True)
            self.hybrid_output_dir = hybrid_result["hybrid_output_dir"]

        self.commands.extend(hybrid_result["commands"])

        # --- Pass 2: Probe Scan (Host) ---
        probe_result = self._run_probe_scan()
        self.probe_output_dir = probe_result["probe_output_dir"]
        self.commands.extend(probe_result["commands"])

        # --- Pass 3: CNN Scoring (Host) ---
        cnn_result = self._run_cnn_scoring()
        self.commands.extend(cnn_result["commands"])

        return {
            "commands": self.commands,
            "hybrid_output_dir": self.hybrid_output_dir,
            "probe_output_dir": self.probe_output_dir,
        }

    def _run_hybrid_detection(self, use_omr: bool = True) -> Dict[str, Any]:
        """Step 2.1: Hybrid Detection (Subprocess or In-Process)"""
        detector = HybridDetector(
            det_cfg=self.det_cfg,
            images=self.images,
            run_id=self.run_id,
            project_root=PROJECT_ROOT,
            dry_run=self.dry_run,
            skip_existing=self.skip_existing,
            in_memory_images=self.in_memory_images,
            use_omr=use_omr,
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
            seed_gen_cfg = self.det_cfg.get("seed_generation")
            
            if seed_gen_cfg:
                logger.info("--- Step 2.2a: Probe Scan Seed Generation (Pass 1) ---")
                probe_seeds_root = self.run_dir / "intermediate" / "probe_seeds"
                ensure_dir(probe_seeds_root)
                
                seed_filter_kwargs = seed_gen_cfg.get("candidate_filter_kwargs", {})
                
                # Use 1x original images for seed generation (Pass 1) to match v12
                # Bypass existing heuristic filters to apply them identically to v12 manually
                run_probe_scan_batch(
                    images=self.images,
                    output_root=probe_seeds_root,
                    bands_from=self.hybrid_output_dir,
                    staff_mask_dir=None,
                    clef_mask_dir=resolved_clef_mask_dir,
                    ink_threshold=int(seed_gen_cfg.get("ink_threshold", 240)),
                    min_ratio=float(seed_gen_cfg.get("min_ratio", 0.10)),
                    min_height_ratio=float(seed_gen_cfg.get("min_height_ratio", 0.0)),
                    min_width_ratio=float(seed_gen_cfg.get("min_width_ratio", 0.0)),
                    score_name=effective_score_name,
                    detect_probe_kwargs={
                        "scan_gap_rescue": True,
                        "scan_gap_threshold_ratio": 1.8,
                        "scan_gap_rescue_min_ratio": 0.0,
                        "scan_gap_margin_ratio": 0.1,
                        "scan_x_peak_rescue": True,
                        "scan_rightmost_rescue": True,
                        "divisi_rescue": True,
                        "scan_x_peak_rescue_mode": "topbottom",
                        "probe_width": 4,
                        "scan_x_peak_ratio_min": 0.0,
                        "scan_rightmost_min_ratio": 0.0,
                        "max_per_band": 100,
                        "scan_center_on_peak": True,
                        "band_scan_line_ratio": 0.6,
                        "band_scan_min_lines": 5,
                        "band_source": "row_stats",
                        "min_peak_distance_unit_ratio": 0.12,
                    },
                    skip_existing=self.skip_existing,
                    input_image_scale=1.0,
                    enable_heuristic_filters=False,
                    disable_seed_splitting=False,
                    in_memory_images=self.in_memory_images,
                )
                
                # Now apply the filters manually to exactly mimic v12
                from src.pipeline.steps.candidate_filters import filter_probe_candidates
                import json
                import cv2
                import numpy as np
                from src.pipeline.utils.images import load_image
                from src.pipeline.core.run_ids import build_probe_run_id

                for img_path in self.images:
                    current_score_name = effective_score_name or img_path.parent.name
                    run_id = build_probe_run_id(img_path, score_name=current_score_name)
                    raw_path = probe_seeds_root / run_id / "pipeline2_no_peak_candidates.json"
                    
                    if not raw_path.exists():
                        continue
                    
                    raw_candidates = []
                    try:
                        raw_candidates = json.loads(raw_path.read_text())
                        (raw_path.parent / "pipeline2_no_peak_candidates_unfiltered.json").write_text(json.dumps(raw_candidates, indent=2))
                    except:
                        continue
                        
                    img = load_image(img_path, in_memory_images=self.in_memory_images)
                    
                    staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
                    mask_path = None
                    injected_dir = seed_gen_cfg.get("staff_mask_injection_dir")
                    
                    if injected_dir:
                        # V12 used line mask debug_3_staff.png. E2E uses regional mask. 
                        # We must fallback to exact v12 mask to recreate baseline accuracy.
                        injected_path = Path(injected_dir)
                        # We want the exact run for this score and page.
                        # e.g. eval2_{score_name}_{page}_YYYYMMDD_HHMMSS
                        # But actually rglob is easier if we just match stem + debug_3_staff.png
                        search_results = list(injected_path.rglob(f"*{current_score_name}*/**/baseline/**/*{img_path.stem}*debug_3_staff.png"))
                        if search_results:
                            mask_path = search_results[0]
                    
                    if not mask_path and resolved_staff_mask_dir:
                        mask_path = resolved_staff_mask_dir / "baseline" / "batch" / img_path.stem / f"{img_path.stem}_staff_mask.png"

                    if mask_path and mask_path.exists():
                        loaded_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
                        if loaded_mask is not None:
                            staff_mask = cv2.resize(loaded_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

                    kept, _ = filter_probe_candidates(
                        candidates=[tuple(int(v) for v in b) for b in raw_candidates],
                        image=img,
                        existing_boxes=[],
                        staff_mask=staff_mask,
                        **seed_filter_kwargs
                    )
                    
                    filtered_path = raw_path.parent / "pipeline2_no_peak_candidates_filtered.json"
                    filtered_path.write_text(json.dumps(kept, indent=2))
                    raw_path.write_text(json.dumps(kept, indent=2)) # we keep this so pass 2 uses the filtered ones!

                self.bands_from_dir = probe_seeds_root
            else:
                self.bands_from_dir = self.hybrid_output_dir

            logger.info("--- Step 2.2b: Probe Scan Generation (Pass 2) ---")
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
                bands_from=self.bands_from_dir,
                staff_mask_dir=None,  # Use row_stats fallback to match v12
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
                in_memory_images=self.in_memory_images,
            )

        # Build command list for logging/return
        cmd_probe = [
            "inprocess:probe_scan",
            "--output-root",
            str(probe_output_root),
            "--bands-from",
            str(self.bands_from_dir if not self.dry_run and seed_gen_cfg else self.hybrid_output_dir),
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
                bands_from=getattr(self, "bands_from_dir", self.hybrid_output_dir),
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
        if self.enable_sr and self.det_cfg.get("use_sr_for_probe", False):
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
        return self.det_cfg.get("probe_score_name", self.run_id)

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
