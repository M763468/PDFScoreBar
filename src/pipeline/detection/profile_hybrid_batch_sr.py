"""Verified hybrid detector with all-pages current-x4 SR phase batching.

The accepted two-HOMR route stays page-local for verified baseline HOMR,
current-x4 HOMR, and OMR-DLN.  Only Real-ESRGAN is lifted into a dedicated
all-pages phase so its model/import/CUDA lifetime is reused and then released
before any page's HOMR/OMR work begins.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.perf_trace import span

from .profile_hybrid import VerifiedProfileHybridDetector, run_homr_profile


class BatchSRVerifiedProfileHybridDetector(VerifiedProfileHybridDetector):
    """Verified profile detector with a dedicated reusable current-SR phase."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._last_sr_batch_result: dict[str, Any] | None = None

    def _support_worker(
        self,
        *,
        image: Path,
        output_root: Path,
        precomputed_sr: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        page_root = output_root / image.parent.name / image.stem
        # The SR batch phase intentionally creates the stable artifacts/sr tree
        # before this page-local worker starts.
        page_root.mkdir(parents=True, exist_ok=True)
        request_path = page_root / "request.json"
        result_path = page_root / "result.json"
        if request_path.exists() or result_path.exists():
            raise FileExistsError(f"Current-support page already materialized: {page_root}")

        request: dict[str, Any] = {
            "schema_version": "pipeline.current_x4_support_request.v2",
            "detection": dict(self.det_cfg),
            "image": str(image.resolve()),
            "output_root": str((page_root / "artifacts").resolve()),
        }
        if precomputed_sr is not None:
            request["precomputed_sr"] = dict(precomputed_sr)
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
        if precomputed_sr is not None and payload.get("sr_execution_scope") != (
            "dedicated_sr_batch_process"
        ):
            raise ValueError("Current x4 support did not consume the dedicated SR batch output")
        return dict(payload), command

    def _generate_one_page_sources_in_process(
        self,
        *,
        image: Path,
        baseline_output: Path,
        support_output: Path,
        precomputed_sr: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate baseline/current support after the optional SR phase has exited."""

        commands: list[list[str]] = []
        baseline_result = run_homr_profile(
            self.profile_name,
            images=[image],
            output_root=baseline_output,
        )
        commands.extend(baseline_result["commands"])

        payload, support_command = self._support_worker(
            image=image,
            output_root=support_output,
            precomputed_sr=precomputed_sr,
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
            "sr_execution_scope": payload.get("sr_execution_scope"),
        }

    def _source_page_worker(
        self,
        *,
        image: Path,
        worker_output: Path,
        baseline_output: Path,
        support_output: Path,
        precomputed_sr: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        page_root = worker_output / image.parent.name / image.stem
        page_root.mkdir(parents=True, exist_ok=False)
        request_path = page_root / "request.json"
        result_path = page_root / "result.json"
        request = {
            "schema_version": "pipeline.verified_source_page_request.v3",
            "detection": dict(self.det_cfg),
            "image": str(image.resolve()),
            "run_id": self.run_id,
            "project_root": str(self.project_root.resolve()),
            "profile_name": self.profile_name,
            "baseline_output": str(baseline_output.resolve()),
            "support_output": str(support_output.resolve()),
            "precomputed_sr": dict(precomputed_sr),
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
        if payload.get("sr_execution_scope") != "dedicated_sr_batch_process":
            raise ValueError("Verified source-page worker did not consume precomputed batch SR")
        if payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError("Verified source-page worker must not use historical artifacts")
        if payload.get("homr_neural_inference_count") != 2:
            raise ValueError("Verified source-page worker must execute exactly two HOMR inferences")
        if payload.get("x4_homr_neural_inference_count") != 1:
            raise ValueError(
                "Verified source-page worker must execute exactly one x4 HOMR inference"
            )
        return dict(payload), command

    def _batch_sr_worker(
        self, *, support_output: Path
    ) -> tuple[dict[Path, dict[str, Any]], list[str], dict[str, Any]]:
        batch_root = support_output / "_sr_batch"
        batch_root.mkdir(parents=True, exist_ok=False)
        request_path = batch_root / "request.json"
        result_path = batch_root / "result.json"

        items: list[dict[str, str]] = []
        for image in self.images:
            output = (
                support_output
                / image.parent.name
                / image.stem
                / "artifacts"
                / "sr"
                / "batch"
                / image.stem
                / image.name
            )
            items.append({"image": str(image.resolve()), "output": str(output.resolve())})

        request = {
            "schema_version": "pipeline.current_x4_sr_batch_request.v1",
            "detection": dict(self.det_cfg),
            "items": items,
        }
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        command = get_pipeline_python("sr") + [
            "-m",
            "src.pipeline.detection.current_sr_batch_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.project_root), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        log_path = batch_root / "worker.log"
        with span("current_support.current_sr_batch_subprocess"):
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
                f"Current x4 SR batch failed ({process.returncode})\n"
                f"--- worker log tail ---\n{tail}"
            )
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete current x4 SR batch result: {result_path}")
        if payload.get("memory_boundary") != "dedicated_sr_batch_process":
            raise ValueError("Current x4 SR batch lacks dedicated-process memory boundary")
        if payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError("Current x4 SR batch must not use historical artifacts")

        by_image: dict[Path, dict[str, Any]] = {}
        for raw in payload.get("outputs", []):
            if not isinstance(raw, Mapping):
                continue
            image = Path(str(raw.get("image", ""))).resolve()
            sr_image = Path(str(raw.get("sr_image", ""))).resolve()
            if not image.is_file() or not sr_image.is_file():
                raise FileNotFoundError(sr_image if image.is_file() else image)
            by_image[image] = dict(raw)
        missing = [str(image) for image in self.images if image.resolve() not in by_image]
        if missing:
            raise ValueError("Current x4 SR batch omitted images: " + ", ".join(missing))
        return by_image, command, dict(payload)

    def _generate_page_sources(
        self,
        *,
        baseline_output: Path,
        support_output: Path,
    ) -> tuple[dict[Path, Path], dict[Path, Path], list[list[str]]]:
        current_sr_detections: dict[Path, Path] = {}
        omr_predictions: dict[Path, Path] = {}
        commands: list[list[str]] = []

        if self.dry_run:
            commands.append(["current-sr-batch-worker", *[str(image) for image in self.images]])
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
                        ["current-support-precomputed-sr", str(image)],
                    ]
                )
            return current_sr_detections, omr_predictions, commands

        precomputed_by_image, batch_command, batch_payload = self._batch_sr_worker(
            support_output=support_output
        )
        self._last_sr_batch_result = batch_payload
        commands.append(batch_command)

        worker_output = baseline_output.parent / "source_page_workers"
        for image in tqdm(self.images, desc="Two-HOMR source generation", unit="page"):
            payload, worker_command = self._source_page_worker(
                image=image,
                worker_output=worker_output,
                baseline_output=baseline_output,
                support_output=support_output,
                precomputed_sr=precomputed_by_image[image.resolve()],
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

    def run(self) -> dict[str, Any]:
        result = super().run()
        result.update(
            {
                "source_generation_scope": "dedicated_sr_batch_then_top_level_python_per_page",
                "sr_model_lifetime": "one_per_detection_call",
                "sr_memory_boundary": "batch_process_exits_before_homr_omr",
                "source_generation_phases": [
                    "current_x4_sr_batch_all_pages",
                    "sr_batch_process_exit",
                    "verified_source_page_worker_per_page",
                    "verified_baseline_per_page",
                    "current_x4_homr_from_precomputed_sr_per_page",
                    "omr_dln_from_precomputed_sr_per_page",
                    "current_x4_detection_reused_for_consensus",
                    "current_consensus",
                ],
            }
        )
        if self._last_sr_batch_result is not None:
            result["current_sr_batch"] = {
                key: self._last_sr_batch_result.get(key)
                for key in (
                    "page_count",
                    "batch_wall_sec",
                    "peak_cuda_allocated_bytes",
                    "peak_cuda_reserved_bytes",
                    "runtime",
                )
            }
        return result
