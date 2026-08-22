"""Hybrid source generation backed by the verified Stage E HOMR profile."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

from tqdm import tqdm

from src.pipeline.perf_trace import span
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from src.pipeline.utils.io import ensure_dir

from .homr_profile import run_homr_profile


class VerifiedProfileHybridDetector:
    """Reconstruct Stage E with one original-image and one x4 HOMR inference.

    Issue #274 keeps the verified HOMR baseline on the original image, but makes
    current x4 support the single owner of x4 HOMR inference. The detector reuses
    the current support worker's source-coordinate ``current_sr_detection`` JSON
    for hybrid consensus instead of rerunning the verified/pinned HOMR profile on
    the same x4 image. Heavy phases remain page-local and are run in a disposable
    top-level Python worker before moving on.
    """

    def __init__(
        self,
        *,
        det_cfg: Dict[str, Any],
        images: list[Path],
        run_id: str,
        project_root: Path,
        dry_run: bool,
        skip_existing: bool,
        in_memory_images: Dict[str, Any] | None = None,
        profile_name: str,
    ) -> None:
        if in_memory_images:
            raise ValueError("Verified HOMR profile requires persisted image files")
        self.det_cfg = det_cfg
        self.images = images
        self.run_id = run_id
        self.project_root = project_root
        self.dry_run = dry_run
        self.skip_existing = skip_existing
        self.profile_name = profile_name

    def _support_worker(
        self,
        *,
        image: Path,
        output_root: Path,
    ) -> tuple[dict[str, Any], list[str]]:
        page_root = output_root / image.parent.name / image.stem
        page_root.mkdir(parents=True, exist_ok=False)
        request_path = page_root / "request.json"
        result_path = page_root / "result.json"
        request = {
            "schema_version": "pipeline.current_x4_support_request.v1",
            "detection": dict(self.det_cfg),
            "image": str(image.resolve()),
            "output_root": str((page_root / "artifacts").resolve()),
        }
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            "-m",
            "src.pipeline.detection.current_support_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.project_root), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        log_path = page_root / "worker.log"
        with span("detector.current_support_worker_parent_wall", fields={"image": str(image)}):
            with log_path.open("w", encoding="utf-8") as log_file:
                process = subprocess.run(
                    command,
                    cwd=self.project_root,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
        if process.returncode != 0:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-60:])
            raise RuntimeError(
                f"Current x4 support failed ({process.returncode}): {image}\n"
                f"--- worker log tail ---\n{tail}"
            )
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete current x4 support result: {result_path}")
        if payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError("Current x4 support must not use historical detector artifacts")
        return dict(payload), command

    @staticmethod
    def _current_detection_path(payload: Mapping[str, Any]) -> Path:
        value = payload.get("current_sr_detection")
        if not value:
            raise ValueError("Current x4 support result lacks current_sr_detection")
        path = Path(str(value)).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _generate_one_page_sources_in_process(
        self,
        *,
        image: Path,
        baseline_output: Path,
        support_output: Path,
    ) -> dict[str, Any]:
        """Generate the two-HOMR source artifacts for one page in this process."""

        commands: list[list[str]] = []
        with span("detector.pinned_original_stage_e_homr_total", fields={"image": str(image)}):
            baseline_result = run_homr_profile(
                self.profile_name,
                images=[image],
                output_root=baseline_output,
            )
        commands.extend(baseline_result["commands"])

        payload, support_command = self._support_worker(
            image=image,
            output_root=support_output,
        )
        sr_image = Path(str(payload["sr_image"])).resolve()
        omr = Path(str(payload["current_omr"])).resolve()
        current_sr_detection = self._current_detection_path(payload)
        for path in (sr_image, omr):
            if not path.is_file():
                raise FileNotFoundError(path)
        commands.append(support_command)

        return {
            "sr_image": str(sr_image),
            "current_sr_detection": str(current_sr_detection),
            "current_omr": str(omr),
            "commands": commands,
            "historical_detector_artifact_runtime_input": False,
            "homr_neural_inference_count": 2,
            "x4_homr_neural_inference_count": 1,
            "x4_detector_support_owner": "current_x4_support",
        }

    def _source_page_worker(
        self,
        *,
        image: Path,
        worker_output: Path,
        baseline_output: Path,
        support_output: Path,
    ) -> tuple[dict[str, Any], list[str]]:
        page_root = worker_output / image.parent.name / image.stem
        page_root.mkdir(parents=True, exist_ok=False)
        request_path = page_root / "request.json"
        result_path = page_root / "result.json"
        request = {
            "schema_version": "pipeline.verified_source_page_request.v2",
            "detection": dict(self.det_cfg),
            "image": str(image.resolve()),
            "run_id": self.run_id,
            "project_root": str(self.project_root.resolve()),
            "profile_name": self.profile_name,
            "baseline_output": str(baseline_output.resolve()),
            "support_output": str(support_output.resolve()),
        }
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            "-m",
            "src.pipeline.detection.verified_source_page_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.project_root), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        log_path = page_root / "worker.log"
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.run(
                command,
                cwd=self.project_root,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if process.returncode != 0:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-80:])
            raise RuntimeError(
                f"Verified source-page worker failed ({process.returncode}): {image}\n"
                f"--- worker log tail ---\n{tail}"
            )
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete verified source-page result: {result_path}")
        if payload.get("memory_boundary") != "top_level_python_per_page":
            raise ValueError(f"Verified source-page worker lacks memory boundary: {result_path}")
        if payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError("Verified source-page worker must not use historical artifacts")
        if payload.get("homr_neural_inference_count") != 2:
            raise ValueError("Verified source-page worker must execute exactly two HOMR inferences")
        if payload.get("x4_homr_neural_inference_count") != 1:
            raise ValueError(
                "Verified source-page worker must execute exactly one x4 HOMR inference"
            )
        return dict(payload), command

    def _generate_page_sources(
        self,
        *,
        baseline_output: Path,
        support_output: Path,
    ) -> tuple[dict[Path, Path], dict[Path, Path], list[list[str]]]:
        """Generate heavy detector sources with one top-level worker per page."""

        current_sr_detections: dict[Path, Path] = {}
        omr_predictions: dict[Path, Path] = {}
        commands: list[list[str]] = []

        if self.dry_run:
            for image in self.images:
                page_root = support_output / image.parent.name / image.stem / "artifacts"
                current_sr_detections[image] = (
                    page_root
                    / "current_homr"
                    / "batch"
                    / image.stem
                    / f"{image.stem}_detections.json"
                )
                omr_predictions[image] = page_root / "omr_sr" / image.stem / "predictions.json"
                commands.extend(
                    [
                        ["verified-source-page-worker", str(image)],
                        ["profile:homr", self.profile_name, "baseline", str(image)],
                        ["current-support", str(image)],
                    ]
                )
            return current_sr_detections, omr_predictions, commands

        worker_output = baseline_output.parent / "source_page_workers"
        for image in tqdm(self.images, desc="Two-HOMR source generation", unit="page"):
            with span(
                "detector.verified_source_page_worker_parent_wall", fields={"image": str(image)}
            ):
                payload, worker_command = self._source_page_worker(
                    image=image,
                    worker_output=worker_output,
                    baseline_output=baseline_output,
                    support_output=support_output,
                )
            current_sr_detection = self._current_detection_path(payload)
            omr = Path(str(payload["current_omr"])).resolve()
            if not omr.is_file():
                raise FileNotFoundError(omr)
            current_sr_detections[image] = current_sr_detection
            omr_predictions[image] = omr
            commands.append(worker_command)
            child_commands = payload.get("commands")
            if isinstance(child_commands, list):
                commands.extend(child_commands)

        return current_sr_detections, omr_predictions, commands

    def run(self) -> Dict[str, Any]:
        hybrid_root = Path(self.det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))
        hybrid_output_dir = hybrid_root / self.run_id
        ensure_dir(hybrid_output_dir)

        if not bool(self.det_cfg.get("enable_sr", True)):
            raise ValueError("The verified Stage E HOMR profile requires detection.enable_sr=true")
        sr_scale = int(self.det_cfg.get("sr_scale", 2))
        if sr_scale != 4:
            raise ValueError(
                f"The verified Stage E HOMR profile requires sr_scale=4, got {sr_scale}"
            )

        for image in self.images:
            if not image.is_file():
                raise FileNotFoundError(image)

        baseline_output = hybrid_output_dir / "baseline"
        support_output = hybrid_output_dir / "current_support"
        hybrid_results_dir = hybrid_output_dir / "hybrid_results"
        ensure_dir(hybrid_results_dir)

        current_sr_detections, omr_predictions, commands = self._generate_page_sources(
            baseline_output=baseline_output,
            support_output=support_output,
        )

        if not self.dry_run:
            for image in tqdm(self.images, desc="Two-HOMR hybrid consensus", unit="page"):
                stem = image.stem
                baseline_json = baseline_output / "batch" / stem / f"{stem}_detections.json"
                sr_json = current_sr_detections[image]
                omr_json = omr_predictions[image]
                output_json = hybrid_results_dir / f"{stem}_hybrid.json"
                missing = [
                    str(path) for path in (baseline_json, sr_json, omr_json) if not path.is_file()
                ]
                if missing:
                    raise FileNotFoundError(
                        f"Two-HOMR hybrid components missing for {stem}: {missing}"
                    )
                with span("detector.hybrid_consensus", fields={"image": str(image)}):
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
            "current_support_output_dir": support_output,
            "historical_detector_artifact_runtime_input": False,
            "source_generation_scope": "top_level_python_per_page",
            "homr_neural_inference_count_per_page": 2,
            "x4_homr_neural_inference_count_per_page": 1,
            "x4_detector_support_owner": "current_x4_support",
            "source_generation_phases": [
                "verified_source_page_worker_per_page",
                "verified_baseline_per_page",
                "current_x4_support_per_page",
                "current_x4_detection_reused_for_consensus",
                "current_consensus",
            ],
        }
