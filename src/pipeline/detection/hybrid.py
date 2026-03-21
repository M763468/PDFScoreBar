"""Hybrid detection engine using Homr and OMR-DLN."""

from __future__ import annotations

import gc
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

import cv2
import torch
from tqdm import tqdm

from homr.main import ProcessingConfig
from homr.music_xml_generator import XmlGeneratorArguments
from src.common.preprocessing import apply_advanced_sr
from src.homr_eval_scripts.core.predictor import HomrPredictor
from src.homr_eval_scripts.core.reporting import save_homr_results
from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import ensure_dir

from .omr_dln import run_omr_dln_batch
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
        in_memory_images: Dict[str, Any] | None = None,
    ):
        self.det_cfg = det_cfg
        self.images = images
        self.run_id = run_id
        self.project_root = project_root
        self.dry_run = dry_run
        self.skip_existing = skip_existing
        self.in_memory_images = in_memory_images

    def run(self) -> Dict[str, Any]:
        """Step 2.1: Hybrid Detection (In-Process homr, In-Process omr-dln)"""
        hybrid_root = Path(self.det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))
        hybrid_output_dir = hybrid_root / self.run_id
        ensure_dir(hybrid_output_dir)

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
        logger.info("--- Step 2.1b: OMR-DLN SR (In-Process) ---")
        sr_root = hybrid_output_dir / "sr" / "batch"
        omr_output = hybrid_output_dir / "omr_sr"

        if not enable_sr:
            logger.info("Skipping OMR-DLN: SR is disabled.")
        elif self.skip_existing and self._omr_all_stems_exist(omr_output, stems):
            logger.info("Skipping OMR-DLN: outputs already exist.")
        else:
            if not self.dry_run:
                run_omr_dln_batch(
                    images=self.images,
                    output_dir=omr_output,
                    pre_computed_sr_dir=sr_root,
                    conf=self.det_cfg.get("omr_conf", 0.25),
                    in_memory_images=self.in_memory_images,
                )

        # 4. Consensus
        logger.info("--- Step 2.1c: Hybrid Consensus Generation ---")
        hybrid_results_dir = hybrid_output_dir / "hybrid_results"
        ensure_dir(hybrid_results_dir)

        for stem in tqdm(stems, desc="Hybrid Consensus", unit="page"):
            baseline_json = hybrid_output_dir / "baseline" / "batch" / stem / f"{stem}_detections.json"
            sr_json = hybrid_output_dir / "sr" / "batch" / stem / f"{stem}_detections.json"
            omr_json = hybrid_output_dir / "omr_sr" / stem / "predictions.json"
            out_json = hybrid_results_dir / f"{stem}_hybrid.json"

            if self.skip_existing and out_json.exists():
                continue

            if not self.dry_run:
                baseline_boxes = load_json_boxes(baseline_json)
                sr_boxes = load_json_boxes(sr_json)
                omr_boxes = load_json_boxes(omr_json)

                hybrid_boxes = apply_hybrid_consensus_filter(
                    baseline_boxes=baseline_boxes,
                    sr_boxes=sr_boxes,
                    omr_boxes=omr_boxes,
                    iou_thresh=float(self.det_cfg.get("hybrid_iou_threshold", 0.5)),
                )
                with open(out_json, "w") as f:
                    json.dump(hybrid_boxes, f)

        return {
            "commands": [["inprocess:homr_hybrid"], ["inprocess:omr_dln"]],
            "hybrid_output_dir": hybrid_output_dir,
        }

    def _omr_all_stems_exist(self, omr_output: Path, stems: List[str]) -> bool:
        for stem in stems:
            if not (omr_output / stem / "predictions.json").exists():
                return False
        return True

    def _run_homr_in_process(self, output_root: Path, enable_sr: bool, sr_scale: int = 2) -> None:
        """Run homr detection in-process."""
        if self.skip_existing and (output_root / "batch").exists():
            logger.info(f"Skipping in-process Homr for {'sr' if enable_sr else 'baseline'}: outputs exist.")
            return

        logger.info(f"--- Homr In-Process Phase 1 (SR={enable_sr}) ---")
        config = ProcessingConfig(
            False, # enable_debug
            True,  # enable_cache
            False, # write_staff_positions
            False, # read_staff_positions
            -1,    # selected_staff
        )
        tuning = DEFAULT_TUNING.copy()
        tuning.update(
            {
                "barline_min_height_factor": self.det_cfg.get("barline_min_height_factor", 1.0),
                "barline_max_width_factor": self.det_cfg.get("barline_max_width_factor", 1.0),
            }
        )

        predictor = HomrPredictor(
            config, 
            tuning, 
            use_gpu_inference=torch.cuda.is_available()
        )
        xml_args = XmlGeneratorArguments(False, None, None)

        try:
            persistent_upsampler = None

            log_vram_usage("Before SR")
            for img in tqdm(self.images, desc="SR/Preparation", unit="page"):
                image_run_dir = output_root / "batch" / img.stem
                ensure_dir(image_run_dir)
                working_path = image_run_dir / img.name
                
                if img.exists():
                    shutil.copy2(img, working_path)
                else:
                    # Support in-memory images: if src doesn't exist on disk, use memory cache
                    img_data = load_image(img, in_memory_images=self.in_memory_images)
                    cv2.imwrite(str(working_path), img_data)

                scale = 1
                if enable_sr:
                    model_name = "RealESRGAN_x4plus" if sr_scale == 4 else "RealESRGAN_x2plus"
                    img_bgr = load_image(working_path, in_memory_images=self.in_memory_images)
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
                        sr_img_path = image_run_dir / f"{img.stem}.png"
                        cv2.imwrite(str(sr_img_path), upscaled)
                        scale = sr_scale
                        # Memory cleanup for large SR images
                        del upscaled
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()

            logger.info("--- Homr In-Process Phase 2 (Inference) ---")
            for img in tqdm(self.images, desc="Homr Inference", unit="page"):
                stem = img.stem
                image_run_dir = output_root / "batch" / stem
                working_path = image_run_dir / img.name
                sr_img_path = image_run_dir / f"{stem}.png"
                
                inference_path = sr_img_path if enable_sr and sr_img_path.exists() else working_path
                scale = sr_scale if enable_sr and sr_img_path.exists() else 1

                if not self.dry_run:
                    # predict returns: (all_preds, xml_path, (h, w), latency, notehead_mask, staff_mask, staff_preds, barline_preds)
                    res = predictor.predict(
                        Path(inference_path),
                        xml_args,
                        sr_scale=scale
                    )
                    metrics_predictions = res[0]
                    notehead_mask = res[4]
                    staff_mask = res[5]

                    save_homr_results(
                        Path(inference_path),
                        image_run_dir,
                        metrics_predictions,
                        notehead_mask,
                        staff_mask
                    )
                    # Coordinates are in inference space, need to scale back to 1x if SR was used
                    if scale > 1:
                        self._rescale_detections(image_run_dir / f"{stem}_detections.json", scale)
                
                log_vram_usage(f"After Page {stem}")

        finally:
            predictor.cleanup()
            log_vram_usage("Final Cleanup")

    def _rescale_detections(self, path: Path, scale: float) -> None:
        if not path.exists():
            return
        with open(path, "r") as f:
            data = json.load(f)
        
        if isinstance(data, dict) and "predictions" in data:
            for pred in data["predictions"]:
                # Do NOT rescale pred_bbox as it is in inference coordinate space
                if "orig_bbox" in pred:
                    pred["orig_bbox"] = [int(round(v / scale)) for v in pred["orig_bbox"]]
        elif isinstance(data, list):
            data = [[int(round(v / scale)) for v in box] for box in data]
            
        with open(path, "w") as f:
            json.dump(data, f)
