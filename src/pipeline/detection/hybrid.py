"""Hybrid detection engine using Homr and OMR-DLN."""

from __future__ import annotations

import concurrent.futures
import gc
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import torch
from tqdm import tqdm

from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from src.pipeline.utils.io import ensure_dir

from .utils import log_vram_usage

try:
    from homr.main import ProcessingConfig
    from homr.music_xml_generator import XmlGeneratorArguments
    from src.common.preprocessing import apply_advanced_sr
    from src.homr_eval_scripts.core.metrics import BarlinePrediction
    from src.homr_eval_scripts.core.predictor import HomrPredictor
    from src.homr_eval_scripts.core.reporting import save_homr_results
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING

    _HOMR_AVAILABLE = True
except ImportError:
    _HOMR_AVAILABLE = False

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
        python_cmd = self._get_python_cmd("homr")
        env = os.environ.copy()
        homr_path = self.project_root / "external" / "homr"
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.project_root), str(homr_path), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)

        experiment_cfg = self._homr_route_parallel_experiment_config()
        baseline_output = hybrid_output_dir / "baseline"
        sr_output = hybrid_output_dir / "sr"
        if experiment_cfg["enabled"]:
            experiment_result = self._run_homr_route_parallel_experiment(
                experiment_cfg=experiment_cfg,
                hybrid_output_dir=hybrid_output_dir,
                baseline_output=baseline_output,
                sr_output=sr_output,
                image_paths=image_paths,
                stems=stems,
                enable_sr=enable_sr,
                python_cmd=python_cmd,
                env=env,
            )
            commands.extend(experiment_result["commands"])
        else:
            # 1. Homr Baseline
            if _HOMR_AVAILABLE:
                self._run_homr_in_process(baseline_output, enable_sr=False)
            elif self.skip_existing and self._all_stems_exist(
                baseline_output, stems, "batch/*/*.json"
            ):
                logger.info("Skipping homr baseline: outputs already exist.")
            else:
                cmd = self._build_homr_baseline_cmd(
                    python_cmd=python_cmd,
                    image_paths=image_paths,
                    output_root=baseline_output,
                )
                commands.append(cmd)
                if not self.dry_run:
                    run_with_logging(cmd, env=env, check=True)

            # 2. Homr SR
            if not enable_sr:
                logger.info("Skipping homr SR: enable_sr is false.")
            elif _HOMR_AVAILABLE:
                self._run_homr_in_process(
                    sr_output, enable_sr=True, sr_scale=int(self.det_cfg.get("sr_scale", 2))
                )
            elif self.skip_existing and self._all_stems_exist(sr_output, stems, "batch/*/*.json"):
                logger.info("Skipping homr SR: outputs already exist.")
            else:
                cmd = self._build_homr_sr_cmd(
                    python_cmd=python_cmd,
                    image_paths=image_paths,
                    output_root=sr_output,
                    sr_scale=int(self.det_cfg.get("sr_scale", 2)),
                )
                commands.append(cmd)
                if not self.dry_run:
                    run_with_logging(cmd, env=env, check=True)

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

    def _build_homr_baseline_cmd(
        self,
        *,
        python_cmd: List[str],
        image_paths: List[str],
        output_root: Path,
    ) -> List[str]:
        return python_cmd + [
            "src/homr_eval_scripts/homr_evaluator.py",
            "--images",
            *image_paths,
            "--output-root",
            self._rel(output_root),
            "--force-run-id",
            "batch",
            "--enable-segnet-cache",
        ]

    def _build_homr_sr_cmd(
        self,
        *,
        python_cmd: List[str],
        image_paths: List[str],
        output_root: Path,
        sr_scale: int,
    ) -> List[str]:
        return python_cmd + [
            "src/homr_eval_scripts/homr_evaluator.py",
            "--images",
            *image_paths,
            "--output-root",
            self._rel(output_root),
            "--force-run-id",
            "batch",
            "--enable-sr",
            "--sr-scale",
            str(sr_scale),
            "--enable-segnet-cache",
        ]

    def _homr_route_parallel_experiment_config(self) -> Dict[str, Any]:
        raw = self.det_cfg.get("homr_route_parallel_experiment", {}) or {}
        if not isinstance(raw, dict):
            raise TypeError("detection.homr_route_parallel_experiment must be a mapping.")
        enabled = bool(raw.get("enabled", False))
        mode = str(raw.get("mode", "baseline_sr_subprocess_overlap"))
        max_workers = int(raw.get("max_workers", 2))
        return {"enabled": enabled, "mode": mode, "max_workers": max_workers}

    def _write_homr_route_experiment_summary(
        self, hybrid_output_dir: Path, summary: Dict[str, Any]
    ) -> Path:
        summary_path = hybrid_output_dir / "homr_route_parallel_experiment_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary_path

    def _run_homr_route_parallel_experiment(
        self,
        *,
        experiment_cfg: Dict[str, Any],
        hybrid_output_dir: Path,
        baseline_output: Path,
        sr_output: Path,
        image_paths: List[str],
        stems: List[str],
        enable_sr: bool,
        python_cmd: List[str],
        env: Dict[str, str],
    ) -> Dict[str, Any]:
        mode = str(experiment_cfg["mode"])
        if mode == "baseline_sr_subprocess_overlap":
            return self._run_homr_subprocess_overlap_experiment(
                experiment_cfg=experiment_cfg,
                hybrid_output_dir=hybrid_output_dir,
                baseline_output=baseline_output,
                sr_output=sr_output,
                image_paths=image_paths,
                stems=stems,
                enable_sr=enable_sr,
                python_cmd=python_cmd,
                env=env,
            )
        if mode == "inprocess_sr_prep_baseline_overlap":
            return self._run_homr_inprocess_sr_prep_baseline_overlap_experiment(
                experiment_cfg=experiment_cfg,
                hybrid_output_dir=hybrid_output_dir,
                baseline_output=baseline_output,
                sr_output=sr_output,
                stems=stems,
                enable_sr=enable_sr,
            )
        raise ValueError(
            "Unsupported homr_route_parallel_experiment.mode "
            f"`{mode}`. Supported: baseline_sr_subprocess_overlap, "
            "inprocess_sr_prep_baseline_overlap."
        )

    def _run_homr_subprocess_overlap_experiment(
        self,
        *,
        experiment_cfg: Dict[str, Any],
        hybrid_output_dir: Path,
        baseline_output: Path,
        sr_output: Path,
        image_paths: List[str],
        stems: List[str],
        enable_sr: bool,
        python_cmd: List[str],
        env: Dict[str, str],
    ) -> Dict[str, Any]:
        """Run the opt-in Issue #163 subprocess overlap experiment for HOMR routes."""
        mode = str(experiment_cfg["mode"])
        if mode != "baseline_sr_subprocess_overlap":
            raise ValueError(
                "Unsupported homr_route_parallel_experiment.mode "
                f"`{mode}`. Supported: baseline_sr_subprocess_overlap."
            )
        max_workers = int(experiment_cfg["max_workers"])
        if max_workers != 2:
            raise ValueError(
                "baseline_sr_subprocess_overlap requires max_workers=2 to keep the "
                "experiment bounded."
            )
        if not enable_sr:
            raise ValueError("baseline_sr_subprocess_overlap requires detection.enable_sr=true.")

        logger.warning(
            "Running opt-in Issue #163 HOMR route experiment: %s. "
            "Default sequential behavior is unchanged unless this config is enabled.",
            mode,
        )

        summary: Dict[str, Any] = {
            "schema_version": "pipeline.detection.homr_route_parallel_experiment.v1",
            "enabled": True,
            "mode": mode,
            "max_workers": max_workers,
            "used_subprocess_route": True,
            "homr_available_in_process": _HOMR_AVAILABLE,
            "status": "started",
            "route_results": [],
        }
        started_at = time.perf_counter()
        commands: List[List[str]] = []
        route_commands: Dict[str, List[str]] = {}

        if self.skip_existing and self._all_stems_exist(baseline_output, stems, "batch/*/*.json"):
            logger.info("Skipping homr baseline: outputs already exist.")
            summary["route_results"].append({"route": "homr_baseline", "status": "skipped_existing"})
        else:
            cmd = self._build_homr_baseline_cmd(
                python_cmd=python_cmd,
                image_paths=image_paths,
                output_root=baseline_output,
            )
            commands.append(cmd)
            route_commands["homr_baseline"] = cmd

        if self.skip_existing and self._all_stems_exist(sr_output, stems, "batch/*/*.json"):
            logger.info("Skipping homr SR: outputs already exist.")
            summary["route_results"].append({"route": "homr_sr", "status": "skipped_existing"})
        else:
            cmd = self._build_homr_sr_cmd(
                python_cmd=python_cmd,
                image_paths=image_paths,
                output_root=sr_output,
                sr_scale=int(self.det_cfg.get("sr_scale", 2)),
            )
            commands.append(cmd)
            route_commands["homr_sr"] = cmd

        if self.dry_run:
            summary["status"] = "dry_run"
            summary["duration_sec"] = time.perf_counter() - started_at
            summary["summary_path"] = str(
                self._write_homr_route_experiment_summary(hybrid_output_dir, summary)
            )
            return {"commands": commands, "summary": summary}

        def run_route(route_name: str, cmd: List[str]) -> Dict[str, Any]:
            route_started_at = time.perf_counter()
            run_with_logging(cmd, env=env, check=True)
            return {
                "route": route_name,
                "status": "completed",
                "duration_sec": time.perf_counter() - route_started_at,
                "command": cmd,
            }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_route = {
                    executor.submit(run_route, route_name, cmd): route_name
                    for route_name, cmd in route_commands.items()
                }
                for future in concurrent.futures.as_completed(future_to_route):
                    summary["route_results"].append(future.result())
            summary["status"] = "completed"
        except Exception as exc:
            summary["status"] = "failed"
            summary["error"] = repr(exc)
            raise
        finally:
            summary["duration_sec"] = time.perf_counter() - started_at
            summary["summary_path"] = str(
                self._write_homr_route_experiment_summary(hybrid_output_dir, summary)
            )

        return {"commands": commands, "summary": summary}

    def _run_homr_inprocess_sr_prep_baseline_overlap_experiment(
        self,
        *,
        experiment_cfg: Dict[str, Any],
        hybrid_output_dir: Path,
        baseline_output: Path,
        sr_output: Path,
        stems: List[str],
        enable_sr: bool,
    ) -> Dict[str, Any]:
        """Overlap only SR image preparation with the baseline in-process HOMR route."""
        mode = str(experiment_cfg["mode"])
        if mode != "inprocess_sr_prep_baseline_overlap":
            raise ValueError(
                "Unsupported homr_route_parallel_experiment.mode "
                f"`{mode}`. Supported: inprocess_sr_prep_baseline_overlap."
            )
        max_workers = int(experiment_cfg["max_workers"])
        if max_workers != 2:
            raise ValueError(
                "inprocess_sr_prep_baseline_overlap requires max_workers=2 to keep the "
                "experiment bounded."
            )
        if not enable_sr:
            raise ValueError("inprocess_sr_prep_baseline_overlap requires detection.enable_sr=true.")
        if not _HOMR_AVAILABLE:
            raise RuntimeError(
                "inprocess_sr_prep_baseline_overlap requires in-process HOMR imports."
            )

        logger.warning(
            "Running opt-in Issue #163 HOMR phase-overlap experiment: %s. "
            "Default sequential behavior is unchanged unless this config is enabled.",
            mode,
        )
        summary: Dict[str, Any] = {
            "schema_version": "pipeline.detection.homr_route_parallel_experiment.v1",
            "enabled": True,
            "mode": mode,
            "max_workers": max_workers,
            "used_subprocess_route": False,
            "homr_available_in_process": _HOMR_AVAILABLE,
            "overlap_granularity": "sr_preparation_vs_baseline_full_route",
            "status": "started",
            "phase_results": [],
        }
        started_at = time.perf_counter()
        commands: List[List[str]] = []

        if self.dry_run:
            summary["status"] = "dry_run"
            summary["duration_sec"] = time.perf_counter() - started_at
            summary["summary_path"] = str(
                self._write_homr_route_experiment_summary(hybrid_output_dir, summary)
            )
            return {"commands": commands, "summary": summary}

        def public_phase_result(result: Dict[str, Any]) -> Dict[str, Any]:
            return {key: value for key, value in result.items() if not key.startswith("_")}

        def run_baseline_route() -> Dict[str, Any]:
            phase_started_at = time.perf_counter()
            if self.skip_existing and self._all_stems_exist(
                baseline_output, stems, "batch/*/*.json"
            ):
                logger.info("Skipping homr baseline: outputs already exist.")
                return {
                    "phase": "homr_baseline_full",
                    "route": "homr_baseline",
                    "status": "skipped_existing",
                    "duration_sec": time.perf_counter() - phase_started_at,
                }
            self._run_homr_in_process(baseline_output, enable_sr=False)
            return {
                "phase": "homr_baseline_full",
                "route": "homr_baseline",
                "status": "completed",
                "duration_sec": time.perf_counter() - phase_started_at,
            }

        def run_sr_preparation() -> Dict[str, Any]:
            phase_started_at = time.perf_counter()
            if self.skip_existing and self._all_stems_exist(sr_output, stems, "batch/*/*.json"):
                logger.info("Skipping homr SR preparation: outputs already exist.")
                return {
                    "phase": "homr_sr_preparation",
                    "route": "homr_sr",
                    "status": "skipped_existing",
                    "duration_sec": time.perf_counter() - phase_started_at,
                    "image_count": 0,
                    "_working_images": [],
                }
            working_images = self._prepare_homr_working_images_only(
                sr_output,
                enable_sr=True,
                sr_scale=int(self.det_cfg.get("sr_scale", 2)),
                phase_label="SR preparation overlap",
            )
            return {
                "phase": "homr_sr_preparation",
                "route": "homr_sr",
                "status": "completed",
                "duration_sec": time.perf_counter() - phase_started_at,
                "image_count": len(working_images),
                "_working_images": working_images,
            }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                baseline_future = executor.submit(run_baseline_route)
                sr_prep_future = executor.submit(run_sr_preparation)
                baseline_result = baseline_future.result()
                sr_prep_result = sr_prep_future.result()

            summary["phase_results"].append(public_phase_result(baseline_result))
            sr_working_images = sr_prep_result.pop("_working_images", [])
            summary["phase_results"].append(public_phase_result(sr_prep_result))

            if sr_prep_result["status"] == "skipped_existing":
                summary["phase_results"].append(
                    {
                        "phase": "homr_sr_inference",
                        "route": "homr_sr",
                        "status": "skipped_existing",
                        "duration_sec": 0.0,
                    }
                )
            else:
                inference_started_at = time.perf_counter()
                self._run_homr_inference_on_working_images(
                    sr_output,
                    working_images=sr_working_images,
                    sr_phase_label="SR inference after preparation overlap",
                )
                summary["phase_results"].append(
                    {
                        "phase": "homr_sr_inference",
                        "route": "homr_sr",
                        "status": "completed",
                        "duration_sec": time.perf_counter() - inference_started_at,
                        "image_count": len(sr_working_images),
                    }
                )

            summary["status"] = "completed"
        except Exception as exc:
            summary["status"] = "failed"
            summary["error"] = repr(exc)
            raise
        finally:
            summary["duration_sec"] = time.perf_counter() - started_at
            summary["summary_path"] = str(
                self._write_homr_route_experiment_summary(hybrid_output_dir, summary)
            )

        return {"commands": commands, "summary": summary}

    def _prepare_homr_working_images_only(
        self,
        output_root: Path,
        *,
        enable_sr: bool,
        sr_scale: int,
        phase_label: str,
    ) -> list[tuple[Path, Path, int]]:
        """Prepare HOMR working images without running HOMR inference."""
        working_images: list[tuple[Path, Path, int]] = []
        persistent_upsampler = None

        from src.pipeline.utils.images import load_image

        logger.info(f"--- Homr In-Process Preparation Only ({phase_label}, SR={enable_sr}) ---")
        log_vram_usage(f"Before {phase_label}")
        try:
            for img in tqdm(self.images, desc="SR/Preparation", unit="page"):
                image_run_dir = output_root / "batch" / img.stem
                ensure_dir(image_run_dir)
                working_path = image_run_dir / img.name

                try:
                    img_bgr = load_image(img, self.in_memory_images)
                except FileNotFoundError as e:
                    logger.warning(f"Failed to prepare {img}: {e}")
                    continue

                scale = 1
                if enable_sr:
                    model_name = "RealESRGAN_x4plus" if sr_scale == 4 else "RealESRGAN_x2plus"
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
                else:
                    cv2.imwrite(str(working_path), img_bgr)
                working_images.append((img, working_path, scale))
        finally:
            persistent_upsampler = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
            log_vram_usage(f"After {phase_label} cleanup")

        return working_images

    def _run_homr_inference_on_working_images(
        self,
        output_root: Path,
        *,
        working_images: list[tuple[Path, Path, int]],
        sr_phase_label: str,
    ) -> None:
        """Run HOMR inference on pre-prepared working images."""
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

        predictor = HomrPredictor(config, tuning, use_gpu_inference=torch.cuda.is_available())
        xml_args = XmlGeneratorArguments(False, None, None)

        try:
            logger.info(f"--- Homr In-Process Phase 2 ({sr_phase_label}) ---")
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

    def _run_homr_in_process(
        self,
        output_root: Path,
        *,
        enable_sr: bool,
        sr_scale: int = 2,
    ) -> None:
        """Runs Homr inference (baseline or SR) in-process for persistence."""
        if not _HOMR_AVAILABLE:
            logger.warning("Homr is not available for in-process execution.")
            return

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

        predictor = HomrPredictor(config, tuning, use_gpu_inference=torch.cuda.is_available())
        xml_args = XmlGeneratorArguments(False, None, None)

        try:
            working_images = []
            persistent_upsampler = None

            from src.pipeline.utils.images import load_image

            logger.info(f"--- Homr In-Process Phase 1 (SR={enable_sr}) ---")
            log_vram_usage("Before SR")
            for img in tqdm(self.images, desc="SR/Preparation", unit="page"):
                image_run_dir = output_root / "batch" / img.stem
                ensure_dir(image_run_dir)
                working_path = image_run_dir / img.name

                try:
                    img_bgr = load_image(img, self.in_memory_images)
                except FileNotFoundError as e:
                    logger.warning(f"Failed to prepare {img}: {e}")
                    continue

                scale = 1
                if enable_sr:
                    model_name = "RealESRGAN_x4plus" if sr_scale == 4 else "RealESRGAN_x2plus"
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
                else:
                    cv2.imwrite(str(working_path), img_bgr)
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
