"""Hybrid detection engine using Homr and OMR-DLN."""

from __future__ import annotations

import gc
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

import cv2
import torch
from src.homr_eval_scripts.core.metrics import BarlinePrediction
from src.homr_eval_scripts.core.predictor import HomrPredictor
from src.homr_eval_scripts.core.reporting import save_homr_results
from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
from tqdm import tqdm

from homr.main import ProcessingConfig
from homr.music_xml_generator import XmlGeneratorArguments
from src.common.preprocessing import apply_advanced_sr
from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from src.pipeline.utils.io import ensure_dir

from .utils import log_vram_usage

logger = logging.getLogger(__name__)


class HybridDetector:
    """Encapsulates hybrid detection logic (Baseline, SR, OMR-DLN)."""

    def __init__(
        self,
        det_cfg: Dict[str, Any],
        images: List[Path],
        run_id: str,
        project_root: Path,
        *,
        dry_run: bool,
        skip_existing: bool = False,
    ):
        self.det_cfg = det_cfg
        self.images = images
        self.run_id = run_id
        self.project_root = project_root
        self.dry_run = dry_run
        self.skip_existing = skip_existing

    def _get_python_cmd(self, name: str) -> List[str]:
        """Returns the appropriate python command, falling back to host if images are external."""
        python_cmd = get_pipeline_python(name)
        if not (python_cmd and python_cmd[0] == "docker"):
            return python_cmd

        for img in self.images:
            try:
                img.resolve().relative_to(self.project_root)
            except ValueError:
                logger.warning(
                    f"External image path detected: {img}. Falling back to host Python for {name}."
                )
                import sys

                return [os.environ.get("PIPELINE_PYTHON", sys.executable)]

        return python_cmd

    def run(self) -> Dict[str, Any]:
        """Step 2.1: Hybrid Detection (Subprocess or In-Process)"""
        hybrid_root = Path(self.det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))
        hybrid_output_dir = hybrid_root / self.run_id
        ensure_dir(hybrid_output_dir)

        image_paths = [self._rel(path) for path in self.images]
        stems = [path.stem for path in self.images]
        commands: List[List[str]] = []

        logger.info("--- Step 2.1: Hybrid Detection (In-Process homr baseline/SR) ---")
        enable_sr = bool(self.det_cfg.get("enable_sr", True))

        # 1. Homr Baseline
        baseline_output = hybrid_output_dir / "baseline"
        self._run_homr_in_process(baseline_output, enable_sr=False)

        # 2. Homr SR
        sr_output = hybrid_output_dir / "sr"
        if not enable_sr:
            logger.info("Skipping homr SR: enable_sr is false.")
        else:
            self._run_homr_in_process(
                sr_output, enable_sr=True, sr_scale=int(self.det_cfg.get("sr_scale", 2))
            )

        # 3. OMR-DLN SR
        logger.info("--- Step 2.1b: OMR-DLN SR (Subprocess) ---")
        sr_root = hybrid_output_dir / "sr" / "batch"
        omr_output = hybrid_output_dir / "omr_sr"

        if not enable_sr:
            logger.info("Skipping OMR-DLN: SR is disabled.")
        elif self.skip_existing and self._omr_all_stems_exist(omr_output, stems):
            logger.info("Skipping OMR-DLN: outputs already exist.")
        else:
            python_cmd_omr = self._get_python_cmd("omr_dln")
            omr_cmd = (
                python_cmd_omr
                + ["experiments/models/eval_omr_dln.py", "--images"]
                + image_paths
                + ["--output-dir", self._rel(omr_output), "--pre-computed-sr", self._rel(sr_root)]
            )
            commands.append(omr_cmd)
            if not self.dry_run:
                env = os.environ.copy()
                env["PYTHONPATH"] = os.pathsep.join(
                    [str(self.project_root), env.get("PYTHONPATH", "")]
                ).strip(os.pathsep)
                run_with_logging(omr_cmd, env=env, check=True)

        # 4. Consensus
        logger.info("--- Step 2.1c: Hybrid Consensus Generation ---")
        hybrid_results_dir = hybrid_output_dir / "hybrid_results"
        ensure_dir(hybrid_results_dir)

        for stem in tqdm(stems, desc="Hybrid Consensus", unit="page"):
            baseline_json = (
                hybrid_output_dir / "baseline" / "batch" / stem / f"{stem}_detections.json"
            )
            sr_json = hybrid_output_dir / "sr" / "batch" / stem / f"{stem}_detections.json"
            omr_json = hybrid_output_dir / "omr_sr" / stem / "predictions.json"
            output_json = hybrid_results_dir / f"{stem}_hybrid.json"

            if not enable_sr:
                if baseline_json.exists():
                    if not self.dry_run:
                        shutil.copy(baseline_json, output_json)
                continue

            if not baseline_json.exists() or not sr_json.exists() or not omr_json.exists():
                logger.warning(f"Missing components for {stem}. Skipping consensus.")
                continue

            if not self.dry_run:
                baseline_boxes = load_json_boxes(baseline_json)
                sr_boxes = load_json_boxes(sr_json)
                omr_boxes = load_json_boxes(omr_json)
                hybrid_preds = apply_hybrid_consensus_filter(
                    baseline_boxes=baseline_boxes,
                    sr_boxes=sr_boxes,
                    omr_boxes=omr_boxes,
                )
                output_json.write_text(json.dumps(hybrid_preds, indent=2))

        return {"commands": commands, "hybrid_output_dir": hybrid_output_dir}

    def _rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.project_root))
        except ValueError:
            return str(path)

    def _all_stems_exist(
        self, base_dir: Path, stems_to_check: List[str], glob_pattern: str
    ) -> bool:
        if not base_dir.exists():
            return False
        found_stems = {p.parent.name for p in base_dir.glob(glob_pattern)}
        return all(s in found_stems for s in stems_to_check)

    def _omr_all_stems_exist(self, omr_output: Path, stems: List[str]) -> bool:
        if not omr_output.exists():
            return False
        found = {p.parent.name for p in omr_output.glob("*/predictions.json")}
        return all(s in found for s in stems)

    def _run_homr_in_process(
        self,
        output_root: Path,
        *,
        enable_sr: bool,
        sr_scale: int = 2,
    ) -> None:
        """Runs Homr inference (baseline or SR) in-process for persistence."""
        stems = [p.stem for p in self.images]
        if self.skip_existing and self._all_stems_exist(output_root, stems, "batch/*/*.json"):
            logger.info(f"Skipping in-process Homr for {output_root.name}: outputs exist.")
            return

        if self.dry_run:
            logger.info(f"Dry run: In-process Homr for {len(self.images)} images -> {output_root}")
            return

        config = ProcessingConfig(
            bool(self.det_cfg.get("enable_debug", False)),
            bool(self.det_cfg.get("enable_cache", True)),
            bool(self.det_cfg.get("write_staff_positions", False)),
            False,
            -1,
            torch.cuda.is_available(),
        )
        tuning = DEFAULT_TUNING.copy()
        tuning.update(
            {
                "barline_min_height_factor": self.det_cfg.get("barline_min_height_factor", 1.0),
                "barline_max_width_factor": self.det_cfg.get("barline_max_width_factor", 1.0),
            }
        )

        predictor = HomrPredictor(config, tuning)
        xml_args = XmlGeneratorArguments(False, None, None)

        try:
            working_images = []
            persistent_upsampler = None

            logger.info(f"--- Homr In-Process Phase 1 (SR={enable_sr}) ---")
            log_vram_usage("Before SR")
            for img in tqdm(self.images, desc="SR/Preparation", unit="page"):
                image_run_dir = output_root / "batch" / img.stem
                ensure_dir(image_run_dir)
                working_path = image_run_dir / img.name
                shutil.copy2(img, working_path)

                scale = 1
                if enable_sr:
                    model_name = "RealESRGAN_x4plus" if sr_scale == 4 else "RealESRGAN_x2plus"
                    img_bgr = cv2.imread(str(working_path))
                    if img_bgr is not None:
                        upscaled, persistent_upsampler = apply_advanced_sr(
                            img_bgr,
                            model_name=model_name,
                            scale=sr_scale,
                            tile=self.det_cfg.get("sr_tile", -1),
                            tile_pad=self.det_cfg.get("sr_tile_pad", 10),
                            fp32=self.det_cfg.get("sr_fp32", False),
                            upsampler=persistent_upsampler,
                        )
                        cv2.imwrite(str(working_path), upscaled)
                        scale = sr_scale
                working_images.append((img, working_path, scale))

            persistent_upsampler = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
            log_vram_usage("After SR Cleanup")

            logger.info("--- Homr In-Process Phase 2 (Inference) ---")
            for original_path, working_path, scale in tqdm(
                working_images, desc="Homr Inference", unit="page"
            ):
                image_run_dir = output_root / "batch" / original_path.stem
                predictions, _, _, _, notehead_mask, staff_mask, _, _ = predictor.predict(
                    working_path, xml_args, sr_scale=scale, image_run_dir=image_run_dir
                )

                metrics_predictions = [
                    BarlinePrediction(
                        pred_bbox=p.pred_bbox,
                        orig_bbox=tuple(int(round(c / scale)) for c in p.orig_bbox),
                        system_index=p.system_index,
                        staff_index=p.staff_index,
                    )
                    for p in predictions
                ]
                save_homr_results(
                    original_path, image_run_dir, metrics_predictions, notehead_mask, staff_mask
                )
                log_vram_usage(f"After Page {original_path.stem}")

        finally:
            predictor.cleanup()
            log_vram_usage("Final Cleanup")
