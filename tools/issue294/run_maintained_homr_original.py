#!/usr/bin/env python3
"""Run maintained HOMR on an original page for Issue #294.

This is an experiment-only worker. It deliberately does not reuse
``current_homr_worker`` because that production support worker requires x4 input
and divides coordinates by four. Here the maintained runtime consumes the
original page with ``sr_scale=1`` so its artifacts stay in original-page space.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

EXPECTED_HOMR_COMMIT = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit() -> str | None:
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={PROJECT_ROOT}",
                "-C",
                str(PROJECT_ROOT),
                "rev-parse",
                "HEAD",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _homr_direct_url() -> dict[str, Any] | None:
    try:
        distribution = importlib.metadata.distribution("homr")
        raw = distribution.read_text("direct_url.json")
        if not raw:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError):
        return None


def _image_shape(path: Path) -> list[int] | None:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return [int(image.shape[1]), int(image.shape[0])]


def _serialize_requested_providers(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _serialize_requested_providers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_requested_providers(item) for item in value]
    return repr(value)


def run(image: Path, output_root: Path, result_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    image = image.resolve()
    output_root = output_root.resolve()
    result_path = result_path.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if output_root.exists():
        raise FileExistsError(output_root)
    if result_path.exists():
        raise FileExistsError(result_path)

    original_shape = _image_shape(image)
    if original_shape is None:
        raise RuntimeError(f"Failed to read source image: {image}")

    import_started = time.perf_counter()
    import homr
    import homr.main as homr_main
    import onnxruntime as ort
    import torch
    from homr.music_xml_generator import XmlGeneratorArguments
    from homr.segmentation import config as segnet_config
    from homr.transformer.configs import Config
    from src.common.connector_artifacts import connector_mask_paths
    from src.homr_eval_scripts.core import heuristics as homr_heuristics
    from src.homr_eval_scripts.core import predictor as homr_predictor
    from src.homr_eval_scripts.core.reporting import save_homr_results
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture
    from src.pipeline.detection.homr_profile_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
    )

    session_records: list[dict[str, Any]] = []
    original_inference_session = ort.InferenceSession

    def recorded_inference_session(path_or_bytes: Any, *args: Any, **kwargs: Any) -> Any:
        requested = kwargs.get("providers")
        if requested is None and len(args) >= 2:
            requested = args[1]
        session = original_inference_session(path_or_bytes, *args, **kwargs)
        session_records.append(
            {
                "model": str(path_or_bytes),
                "requested_providers": _serialize_requested_providers(requested),
                "active_providers": list(session.get_providers()),
            }
        )
        return session

    ort.InferenceSession = recorded_inference_session
    use_gpu_inference = bool(torch.cuda.is_available())
    compat_modes = install_current_homr_consumer_compat(
        homr_main,
        homr_predictor,
        homr_heuristics,
        use_gpu_inference=use_gpu_inference,
    )
    connector_capture_installed = install_homr_connector_artifact_capture(
        homr_predictor.HomrPredictor
    )
    imports_and_compat_sec = time.perf_counter() - import_started

    config = build_processing_config_compat(
        homr_main.ProcessingConfig,
        enable_debug=False,
        enable_cache=True,
        write_staff_positions=False,
        use_gpu_inference=use_gpu_inference,
    )
    tuning = DEFAULT_TUNING.copy()
    xml_args = XmlGeneratorArguments(False, None, None)

    predictor_started = time.perf_counter()
    predictor = homr_predictor.HomrPredictor(
        config,
        tuning,
        use_gpu_inference=use_gpu_inference,
    )
    predictor_init_sec = time.perf_counter() - predictor_started

    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=False)
    try:
        predict_started = time.perf_counter()
        (
            predictions,
            _xml_path,
            _seg_shape,
            homr_core_sec,
            notehead_mask,
            staff_mask,
            _rejected,
            _added,
        ) = predictor.predict(
            image,
            xml_args,
            sr_scale=1,
            image_run_dir=image_run_dir,
        )
        predict_wall_sec = time.perf_counter() - predict_started

        serialization_started = time.perf_counter()
        detection = save_homr_results(
            image,
            image_run_dir,
            predictions,
            notehead_mask,
            staff_mask,
        )
        serialization_sec = time.perf_counter() - serialization_started
    finally:
        predictor.cleanup()
        ort.InferenceSession = original_inference_session

    staff = image_run_dir / f"{stem}_staff_mask.png"
    notehead = image_run_dir / f"{stem}_notehead_mask.png"
    proxy = image_run_dir / f"{stem}_proxy.png"
    connector_paths = connector_mask_paths(image_run_dir, stem)
    connector_complete = all(path.is_file() for path in connector_paths.values())

    transformer_paths = Config().filepaths
    model_paths = {
        "segnet_fp16": Path(segnet_config.segnet_path_onnx_fp16),
        "transformer_encoder_fp16": Path(transformer_paths.encoder_path_fp16),
        "transformer_decoder_fp16": Path(transformer_paths.decoder_path_fp16),
    }
    model_provenance = {
        name: {
            "path": str(path),
            "exists": path.is_file(),
            "sha256": sha256(path) if path.is_file() else None,
        }
        for name, path in model_paths.items()
    }

    direct_url = _homr_direct_url()
    installed_commit = None
    if isinstance(direct_url, dict):
        vcs_info = direct_url.get("vcs_info")
        if isinstance(vcs_info, dict):
            installed_commit = vcs_info.get("commit_id")

    mask_shapes = {
        "staff": _image_shape(staff),
        "notehead": _image_shape(notehead),
    }
    payload = {
        "schema_version": "issue294.maintained_original_homr.v1",
        "status": "completed",
        "historical_detector_artifact_runtime_input": False,
        "input_contract": {
            "image": str(image),
            "original_shape_wh": original_shape,
            "sr_scale": 1,
            "coordinate_space": "original_page",
            "proxy_path": str(proxy) if proxy.is_file() else None,
            "proxy_shape_wh": _image_shape(proxy) if proxy.is_file() else original_shape,
        },
        "runtime": {
            "python": sys.executable,
            "python_version": platform.python_version(),
            "source_commit": _source_commit(),
            "homr_module": str(Path(str(homr.__file__)).resolve()),
            "homr_expected_commit": EXPECTED_HOMR_COMMIT,
            "homr_installed_commit": installed_commit,
            "homr_direct_url": direct_url,
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "torch_version": torch.__version__,
            "torch_cuda_available": use_gpu_inference,
            "onnxruntime_version": ort.__version__,
            "onnxruntime_available_providers": list(ort.get_available_providers()),
            "compatibility": compat_modes,
            "connector_capture_installed": connector_capture_installed,
        },
        "models": model_provenance,
        "onnx_sessions": session_records,
        "timings_sec": {
            "imports_and_compat": imports_and_compat_sec,
            "predictor_init": predictor_init_sec,
            "predict_wall": predict_wall_sec,
            "homr_core": float(homr_core_sec),
            "predict_residual": max(0.0, predict_wall_sec - float(homr_core_sec)),
            "serialization": serialization_sec,
            "worker_total": time.perf_counter() - started,
        },
        "artifacts": {
            "detections": str(detection),
            "staff_mask": str(staff),
            "notehead_mask": str(notehead),
            "connector_symbols": (
                str(connector_paths["symbols"]) if connector_paths["symbols"].is_file() else None
            ),
            "connector_brace_dot": (
                str(connector_paths["brace_dot"])
                if connector_paths["brace_dot"].is_file()
                else None
            ),
            "connector_complete": connector_complete,
        },
        "coordinate_checks": {
            "staff_mask_shape_wh": mask_shapes["staff"],
            "notehead_mask_shape_wh": mask_shapes["notehead"],
            "masks_match_original_shape": all(
                shape == original_shape for shape in mask_shapes.values()
            ),
        },
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.image, args.output_root, args.result)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "result": str(args.result.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
