"""Hybrid detector route backed by the verified Stage E HOMR profile."""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path
from typing import Any, Dict

import cv2
import torch
from tqdm import tqdm

from src.common.preprocessing import apply_advanced_sr
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import ensure_dir

from .homr_profile import run_homr_profile
from .hybrid import HybridDetector


class VerifiedProfileHybridDetector(HybridDetector):
    """Use the pinned HOMR profile while retaining current SR/OMR/consensus code."""

    def __init__(self, *args: Any, profile_name: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.profile_name = profile_name

    def _generate_sr_sources(self, output_root: Path, *, sr_scale: int) -> dict[Path, Path]:
        """Generate fresh SR images inside the page-isolated detector process."""
        if sr_scale not in (2, 4):
            raise ValueError(f"Unsupported SR scale for verified profile: {sr_scale}")
        if self.dry_run:
            return {image: output_root / "batch" / image.stem / image.name for image in self.images}

        model_name = "RealESRGAN_x4plus" if sr_scale == 4 else "RealESRGAN_x2plus"
        generated: dict[Path, Path] = {}
        persistent_upsampler = None
        try:
            for image in tqdm(self.images, desc="Verified profile SR", unit="page"):
                if not image.is_file():
                    raise FileNotFoundError(image)
                image_run_dir = output_root / "batch" / image.stem
                ensure_dir(image_run_dir)
                working_path = image_run_dir / image.name
                image_bgr = load_image(image, self.in_memory_images)
                upscaled, persistent_upsampler = apply_advanced_sr(
                    image_bgr,
                    model_name=model_name,
                    scale=sr_scale,
                    tile=self.det_cfg.get("sr_tile", -1),
                    tile_pad=self.det_cfg.get("sr_tile_pad", 10),
                    fp32=self.det_cfg.get("sr_fp32", False),
                    upsampler=persistent_upsampler,
                )
                if not cv2.imwrite(str(working_path), upscaled):
                    raise RuntimeError(f"Failed to write SR image: {working_path}")
                generated[image] = working_path
                del upscaled
                del image_bgr
        finally:
            persistent_upsampler = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        return generated

    def run(self) -> Dict[str, Any]:
        hybrid_root = Path(self.det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))
        hybrid_output_dir = hybrid_root / self.run_id
        ensure_dir(hybrid_output_dir)

        image_paths = [self._rel(path) for path in self.images]
        stems = [path.stem for path in self.images]
        commands: list[list[str]] = []
        enable_sr = bool(self.det_cfg.get("enable_sr", True))
        if not enable_sr:
            raise ValueError("The verified Stage E HOMR profile requires detection.enable_sr=true")
        sr_scale = int(self.det_cfg.get("sr_scale", 2))

        baseline_output = hybrid_output_dir / "baseline"
        sr_source_output = hybrid_output_dir / "sr_source"
        sr_output = hybrid_output_dir / "sr"

        if not self.dry_run:
            baseline_result = run_homr_profile(
                self.profile_name,
                images=self.images,
                output_root=baseline_output,
            )
            commands.extend(baseline_result["commands"])
            sr_sources = self._generate_sr_sources(sr_source_output, sr_scale=sr_scale)
            sr_result = run_homr_profile(
                self.profile_name,
                images=self.images,
                output_root=sr_output,
                precomputed_sr=sr_sources,
            )
            commands.extend(sr_result["commands"])
        else:
            sr_sources = self._generate_sr_sources(sr_source_output, sr_scale=sr_scale)
            commands.append(["profile:homr", self.profile_name, "baseline"])
            commands.append(["profile:homr", self.profile_name, f"sr_x{sr_scale}"])

        # Keep OMR-DLN on the current production runtime. It consumes the SR image
        # copied into the canonical profile SR output tree by the evaluator.
        omr_output = hybrid_output_dir / "omr_sr"
        python_cmd_omr = self._get_python_cmd("omr_dln")
        omr_cmd = (
            python_cmd_omr
            + ["experiments/models/eval_omr_dln.py", "--images"]
            + image_paths
            + [
                "--output-dir",
                self._rel(omr_output),
                "--pre-computed-sr",
                self._rel(sr_output / "batch"),
            ]
        )
        commands.append(omr_cmd)
        if not self.dry_run:
            env = os.environ.copy()
            homr_path = self.project_root / "external" / "homr"
            env["PYTHONPATH"] = os.pathsep.join(
                [str(self.project_root), str(homr_path), env.get("PYTHONPATH", "")]
            ).strip(os.pathsep)
            run_with_logging(omr_cmd, env=env, check=True)

        hybrid_results_dir = hybrid_output_dir / "hybrid_results"
        ensure_dir(hybrid_results_dir)
        if not self.dry_run:
            for stem in tqdm(stems, desc="Hybrid Consensus", unit="page"):
                baseline_json = baseline_output / "batch" / stem / f"{stem}_detections.json"
                sr_json = sr_output / "batch" / stem / f"{stem}_detections.json"
                omr_json = omr_output / stem / "predictions.json"
                output_json = hybrid_results_dir / f"{stem}_hybrid.json"
                missing = [
                    str(path) for path in (baseline_json, sr_json, omr_json) if not path.is_file()
                ]
                if missing:
                    raise FileNotFoundError(
                        f"Verified-profile hybrid components missing for {stem}: {missing}"
                    )
                hybrid_preds = apply_hybrid_consensus_filter(
                    baseline_boxes=load_json_boxes(baseline_json),
                    sr_boxes=load_json_boxes(sr_json),
                    omr_boxes=load_json_boxes(omr_json),
                )
                output_json.write_text(
                    json.dumps(hybrid_preds, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

        return {
            "commands": commands,
            "hybrid_output_dir": hybrid_output_dir,
            "homr_profile": self.profile_name,
            "sr_source_output_dir": sr_source_output,
            "historical_detector_artifact_runtime_input": False,
        }
