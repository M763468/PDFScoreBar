#!/usr/bin/env python3
"""Audit the primary HOMR runtime contract for Issue #274 without rerunning inference.

This experiment is intentionally inference-free. It answers three questions before
we run another HOMR page:

1. Did retained current-core B pages load HOMR prediction (.npy) caches, or did
   they perform fresh SegNet inference and only save a cache afterwards?
2. Do the current and pinned runtimes resolve the same HOMR source files and model
   binaries, or does the shared commit marker hide source/model drift?
3. What configuration differences remain between the two producer entrypoints?

The output is diagnostic provenance, not an accuracy experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from src.pipeline.detection.current_support_worker import _build_worker_environment
from src.pipeline.detection.homr_profile import (
    build_profile_environment,
    load_homr_profile,
)
from tools.issue274.analyze_x4_support_contract import load_json, to_workspace


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    result: dict[str, Any] = {
        "path": str(resolved),
        "exists": resolved.is_file(),
    }
    if resolved.is_file():
        stat = resolved.stat()
        result.update(
            {
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": sha256(resolved),
            }
        )
    return result


RUNTIME_PROBE = r"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import json
import sys
from pathlib import Path


def file_sha(path):
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def module_row(name):
    row = {"module": name}
    try:
        spec = importlib.util.find_spec(name)
        row["found"] = spec is not None
        row["origin"] = None if spec is None else spec.origin
        if spec is not None and spec.origin:
            row["sha256"] = file_sha(spec.origin)
        if spec is not None and spec.submodule_search_locations is not None:
            row["search_locations"] = list(spec.submodule_search_locations)
    except Exception as exc:
        row["error"] = repr(exc)
    return row


def signature_row(module_name, symbol):
    row = {"module": module_name, "symbol": symbol}
    try:
        module = importlib.import_module(module_name)
        value = module
        for part in symbol.split("."):
            value = getattr(value, part)
        row["signature"] = str(inspect.signature(value))
    except Exception as exc:
        row["error"] = repr(exc)
    return row

modules = [
    "homr",
    "homr.main",
    "homr.segmentation.config",
    "homr.segmentation.inference_segnet",
    "homr.resize",
    "homr.color_adjust",
    "homr.noise_filtering",
    "homr.bounding_boxes",
    "homr.bar_line_detection",
    "homr.staff_detection",
    "src.homr_eval_scripts.homr_evaluator",
    "src.homr_eval_scripts.core.predictor",
    "src.homr_eval_scripts.core.heuristics",
    "src.homr_eval_scripts.segnet_cache",
]

payload = {
    "python": sys.executable,
    "version": sys.version,
    "sys_path": sys.path,
    "modules": [module_row(name) for name in modules],
    "signatures": [
        signature_row("homr.main", "ProcessingConfig"),
        signature_row("homr.main", "download_weights"),
        signature_row("homr.main", "load_and_preprocess_predictions"),
        signature_row("homr.segmentation.inference_segnet", "Segnet"),
        signature_row("homr.segmentation.inference_segnet", "extract"),
    ],
    "packages": {},
    "segmentation": {},
}

for name in ("numpy", "opencv-python", "onnxruntime-gpu", "onnxruntime", "torch"):
    try:
        payload["packages"][name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        payload["packages"][name] = None

try:
    cfg = importlib.import_module("homr.segmentation.config")
    for key in (
        "segmentation_version",
        "segnet_path_onnx",
        "segnet_path_onnx_fp16",
    ):
        value = getattr(cfg, key, None)
        if value is None:
            payload["segmentation"][key] = None
            continue
        if key.startswith("segnet_path"):
            p = Path(str(value))
            payload["segmentation"][key] = {
                "path": str(p),
                "exists": p.is_file(),
                "sha256": file_sha(p),
                "size_bytes": p.stat().st_size if p.is_file() else None,
            }
        else:
            payload["segmentation"][key] = value
except Exception as exc:
    payload["segmentation"]["error"] = repr(exc)

print(json.dumps(payload, ensure_ascii=False))
"""


def run_probe(*, python: Path, env: Mapping[str, str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(python), "-c", RUNTIME_PROBE],
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "error": f"probe JSON decode failed: {exc}",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    return {"status": "completed", **payload}


def classify_cache_log(text: str) -> str:
    if "Loading from cache" in text:
        return "loaded_prediction_cache"
    if "Saving cache" in text and "Starting Inference" in text:
        return "fresh_inference_then_saved_prediction_cache"
    if "Starting Inference" in text:
        return "fresh_inference_no_prediction_cache_save_marker"
    if "Found a cache" in text:
        return "cache_found_but_not_loaded_or_log_incomplete"
    return "no_cache_or_inference_marker"


def cache_page_row(record: Mapping[str, Any], workspace: Path) -> dict[str, Any]:
    score = str(record["score"])
    page = str(record["page"])
    b_path = to_workspace(record["b_current_x4_path"], workspace)
    c_path = to_workspace(record["c_pinned_x4_path"], workspace)
    artifact_root = b_path.parents[3]
    log_path = artifact_root / "current_homr_worker.log"
    request_path = artifact_root / "current_homr_request.json"
    result_path = artifact_root / "current_homr_result.json"

    log_text = ""
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")

    b_npy = sorted((artifact_root / "current_homr").rglob("*.npy"))
    c_run_dir = c_path.parent
    c_npy = sorted(c_run_dir.rglob("*.npy")) if c_run_dir.is_dir() else []

    request = load_json(request_path) if request_path.is_file() else None
    det_cfg = request.get("detection") if isinstance(request, dict) else None

    return {
        "score": score,
        "page": page,
        "b_detection": str(b_path),
        "c_detection": str(c_path),
        "current_artifact_root": str(artifact_root),
        "current_log": artifact(log_path),
        "current_request": artifact(request_path),
        "current_result": artifact(result_path),
        "cache_classification": classify_cache_log(log_text),
        "log_markers": {
            "found_cache": log_text.count("Found a cache"),
            "loading_cache": log_text.count("Loading from cache"),
            "saving_cache": log_text.count("Saving cache"),
            "starting_inference": log_text.count("Starting Inference"),
            "creating_proxy": log_text.count("Creating Proxy"),
        },
        "current_prediction_cache_files": [artifact(path) for path in b_npy],
        "verified_c_npy_files_below_detection_dir": [artifact(path) for path in c_npy],
        "current_detection_config": det_cfg,
    }


def module_map(runtime: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    modules = runtime.get("modules")
    if not isinstance(modules, list):
        return result
    for row in modules:
        if isinstance(row, dict) and isinstance(row.get("module"), str):
            result[str(row["module"])] = row
    return result


def compare_runtime_probes(current: Mapping[str, Any], pinned: Mapping[str, Any]) -> dict[str, Any]:
    current_modules = module_map(current)
    pinned_modules = module_map(pinned)
    names = sorted(set(current_modules) | set(pinned_modules))
    rows = []
    for name in names:
        left = current_modules.get(name, {})
        right = pinned_modules.get(name, {})
        rows.append(
            {
                "module": name,
                "current_origin": left.get("origin"),
                "pinned_origin": right.get("origin"),
                "current_sha256": left.get("sha256"),
                "pinned_sha256": right.get("sha256"),
                "same_sha256": bool(
                    left.get("sha256")
                    and right.get("sha256")
                    and left.get("sha256") == right.get("sha256")
                ),
            }
        )

    current_seg = current.get("segmentation", {})
    pinned_seg = pinned.get("segmentation", {})
    return {
        "modules": rows,
        "segmentation_version_equal": (
            isinstance(current_seg, dict)
            and isinstance(pinned_seg, dict)
            and current_seg.get("segmentation_version") == pinned_seg.get("segmentation_version")
        ),
        "current_segmentation": current_seg,
        "pinned_segmentation": pinned_seg,
        "current_signatures": current.get("signatures"),
        "pinned_signatures": pinned.get("signatures"),
        "current_packages": current.get("packages"),
        "pinned_packages": pinned.get("packages"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ab-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/issue274_homr_x4_stage_e_ab.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/primary_runtime_contract_01/"
            "issue274_primary_homr_runtime_contract.json"
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    output_path = to_workspace(args.output, workspace)

    ab = load_json(ab_path)
    page_records = ab["hybrid_ab"]["pages"]
    if len(page_records) != 68:
        raise RuntimeError(f"Expected 68 retained pages, got {len(page_records)}")

    cache_rows = [cache_page_row(record, workspace) for record in page_records]
    cache_counts = Counter(row["cache_classification"] for row in cache_rows)

    profile = load_homr_profile("stage_e_verified")
    runtime = profile["runtime"]
    if not isinstance(runtime, Mapping):
        raise RuntimeError("stage_e_verified runtime is invalid")

    current_python = Path("/opt/venv_pipeline/bin/python")
    pinned_python = Path(str(runtime["python"]))
    if not current_python.is_file():
        raise FileNotFoundError(current_python)
    if not pinned_python.is_file():
        raise FileNotFoundError(pinned_python)

    current_env = _build_worker_environment()
    pinned_env = build_profile_environment(profile)

    current_probe = run_probe(python=current_python, env=current_env, cwd=workspace)
    pinned_probe = run_probe(python=pinned_python, env=pinned_env, cwd=workspace)

    config_rows = []
    for row in cache_rows:
        det_cfg = row.get("current_detection_config")
        if isinstance(det_cfg, dict):
            config_rows.append(det_cfg)
    unique_current_configs = []
    seen = set()
    for cfg in config_rows:
        marker = json.dumps(cfg, sort_keys=True, ensure_ascii=False, default=str)
        if marker not in seen:
            seen.add(marker)
            unique_current_configs.append(cfg)

    result = {
        "schema_version": "issue274.primary_homr_runtime_contract.v1",
        "status": "completed",
        "scope": {
            "pages": 68,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
            "runtime_import_probes_only": True,
        },
        "retained_b_prediction_cache": {
            "classification_counts": dict(cache_counts),
            "pages": cache_rows,
        },
        "runtime_probe": {
            "current": current_probe,
            "pinned": pinned_probe,
            "comparison": compare_runtime_probes(current_probe, pinned_probe),
        },
        "entrypoint_contract": {
            "current_b": {
                "entrypoint": "src.pipeline.detection.current_homr_worker -> core.HomrPredictor",
                "processing_config": {
                    "enable_debug": "detection.enable_debug default false",
                    "enable_cache": "detection.enable_cache default true",
                    "write_staff_positions": "detection.write_staff_positions default false",
                    "use_gpu_inference": "torch.cuda.is_available()",
                },
                "unique_retained_detection_configs": unique_current_configs,
            },
            "verified_c": {
                "entrypoint": "homr_profile_compat -> homr_evaluator.run_evaluation",
                "profile_command_flags": ["--enable-segnet-cache", "--pre-computed-sr"],
                "processing_config": {
                    "enable_debug": True,
                    "enable_cache": False,
                    "reason_enable_cache_false": "profile command does not pass homr_evaluator --cache",
                    "use_gpu_inference": "torch.cuda.is_available() / compatibility boundary",
                },
            },
            "important_distinction": (
                "--enable-segnet-cache patches ONNXRuntime session construction; "
                "ProcessingConfig.enable_cache controls HOMR prediction .npy reuse."
            ),
        },
        "decision_rule": {
            "if_b_loaded_prediction_cache": (
                "Treat cache provenance as a candidate primary-output cause and rerun one page cache-off/on."
            ),
            "if_homr_module_hashes_differ": (
                "The shared commit marker is insufficient; first normalize the HOMR source tree before accuracy tuning."
            ),
            "if_model_hashes_differ": (
                "Normalize model artifacts before comparing producer algorithms."
            ),
            "if_sources_models_same_and_b_fresh": (
                "Run one page with stage captures at raw SegNet masks -> predict_symbols -> primary barline boxes -> mapped pre-thin boxes, "
                "using monolithic and core entrypoints in the same current runtime."
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "cache_classification_counts": dict(cache_counts),
                "current_probe_status": current_probe.get("status"),
                "pinned_probe_status": pinned_probe.get("status"),
                "output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
