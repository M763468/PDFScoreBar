#!/usr/bin/env python3
"""Probe the pinned Stage-E HOMR runtime after Issue #294 timing runs.

Run this with ``/opt/venv_stage_e_homr/bin/python``. It does not execute page
inference. It loads the three pinned ONNX models to verify hashes and actual
execution providers without warming only variant A before the causal timing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import platform
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "configs/detector_profiles/stage_e_verified_homr.json"
EXPECTED_PROFILE = "stage_e_verified"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_profile() -> dict[str, Any]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("name") != EXPECTED_PROFILE:
        raise ValueError(f"Unexpected HOMR profile: {PROFILE_PATH}")
    return payload


def install_profile_paths(profile: dict[str, Any]) -> dict[str, str]:
    runtime = profile.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("Stage-E profile lacks runtime")
    homr_source = Path(str(runtime["homr_source"])).resolve()
    pdfscore_source = Path(str(runtime["pdfscore_source"])).resolve()
    entries = [
        str(homr_source),
        str(pdfscore_source),
        str(pdfscore_source / "src"),
        str(PROJECT_ROOT),
    ]
    for entry in reversed(entries):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return {str(key): str(value) for key, value in runtime.items()}


def validate_markers(profile: dict[str, Any], runtime: dict[str, str]) -> dict[str, Any]:
    homr_expected = str(profile["homr"]["commit"])
    pdfscore_expected = str(profile["pdfscore_evaluator"]["commit"])
    homr_actual = Path(runtime["homr_commit_marker"]).read_text(encoding="utf-8").strip()
    pdfscore_actual = Path(runtime["pdfscore_commit_marker"]).read_text(encoding="utf-8").strip()
    return {
        "homr_expected": homr_expected,
        "homr_actual": homr_actual,
        "homr_match": homr_actual == homr_expected,
        "pdfscore_expected": pdfscore_expected,
        "pdfscore_actual": pdfscore_actual,
        "pdfscore_match": pdfscore_actual == pdfscore_expected,
    }


def load_workspace_compat() -> Any:
    path = PROJECT_ROOT / "src/pipeline/detection/homr_profile_compat.py"
    spec = importlib.util.spec_from_file_location("issue294_workspace_homr_compat", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load compatibility module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serialize_requested(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): serialize_requested(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_requested(item) for item in value]
    return repr(value)


def _construct_segnet(segnet_cls: type[Any], model_path: str, use_gpu: bool) -> Any:
    signature = inspect.signature(segnet_cls)
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and parameter.default is inspect.Parameter.empty
    ]
    if len(required) <= 1:
        return segnet_cls(use_gpu)
    return segnet_cls(model_path, use_gpu)


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    profile = load_profile()
    runtime_paths = install_profile_paths(profile)
    markers = validate_markers(profile, runtime_paths)

    import cv2
    import homr
    import numpy as np
    import onnxruntime as ort
    from homr.segmentation.config import segnet_path_onnx
    from homr.segmentation.inference_segnet import Segnet
    from homr.transformer.configs import Config
    from homr.transformer.decoder_inference import get_decoder
    from homr.transformer.encoder_inference import Encoder
    from src.homr_eval_scripts import homr_evaluator

    compat = load_workspace_compat()
    compatibility = compat.install_homr_api_compat(homr_evaluator)

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
                "requested_providers": serialize_requested(requested),
                "active_providers": list(session.get_providers()),
            }
        )
        return session

    ort.InferenceSession = recorded_inference_session
    use_gpu = "CUDAExecutionProvider" in ort.get_available_providers()
    config = Config()
    try:
        segnet = _construct_segnet(Segnet, str(segnet_path_onnx), use_gpu)
        encoder = Encoder(config.filepaths.encoder_path, use_gpu)
        decoder = get_decoder(config, config.filepaths.decoder_path, use_gpu)
        _ = (segnet, encoder, decoder)
    finally:
        ort.InferenceSession = original_inference_session

    expected_models = profile.get("models")
    if not isinstance(expected_models, list):
        raise ValueError("Stage-E profile lacks model provenance")
    homr_root = Path(runtime_paths["homr_source"])
    models: list[dict[str, Any]] = []
    for item in expected_models:
        if not isinstance(item, dict):
            continue
        relative = Path(str(item["path"]))
        path = homr_root / relative
        actual_hash = sha256(path) if path.is_file() else None
        expected_hash = str(item.get("sha256", ""))
        models.append(
            {
                "path": str(path),
                "exists": path.is_file(),
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "sha256_match": actual_hash == expected_hash,
            }
        )

    required_roles = {"segnet": False, "encoder": False, "decoder": False}
    role_cuda_first = dict(required_roles)
    for record in session_records:
        name = Path(str(record["model"])).name.lower()
        if "segnet" in name:
            role = "segnet"
        elif name.startswith("encoder_"):
            role = "encoder"
        elif name.startswith("decoder_"):
            role = "decoder"
        else:
            continue
        required_roles[role] = True
        providers = record.get("active_providers")
        role_cuda_first[role] = bool(
            isinstance(providers, list)
            and providers
            and providers[0] == "CUDAExecutionProvider"
        )

    payload = {
        "schema_version": "issue294.pinned_homr_runtime_probe.v1",
        "status": "completed",
        "profile": profile,
        "runtime": {
            "python": sys.executable,
            "python_version": platform.python_version(),
            "homr_module": str(Path(str(homr.__file__)).resolve()),
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "onnxruntime_version": ort.__version__,
            "onnxruntime_available_providers": list(ort.get_available_providers()),
            "compatibility": compatibility,
        },
        "commit_markers": markers,
        "models": models,
        "onnx_sessions": session_records,
        "provider_roles_seen": required_roles,
        "provider_roles_cuda_first": role_cuda_first,
        "hard_contract_pass": (
            markers["homr_match"]
            and markers["pdfscore_match"]
            and bool(models)
            and all(item["sha256_match"] for item in models)
            and all(required_roles.values())
            and all(role_cuda_first.values())
        ),
        "inference_executed": False,
        "historical_detector_artifact_runtime_input": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.output.resolve())
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
                "output": str(args.output.resolve()),
                "hard_contract_pass": payload["hard_contract_pass"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
