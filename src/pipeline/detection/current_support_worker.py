"""Generate current x4/HOMR/OMR support for one detector page.

The current support path preserves connector-semantic HOMR artifacts.  SR may be
materialized by a dedicated all-pages SR process before this worker starts; the
current HOMR and OMR-DLN phases remain page-local and process-isolated so no
Real-ESRGAN model state overlaps their GPU lifetime.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.perf_trace import set_context, span

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-support request must be a mapping")
    return dict(payload)


def _load_completed_result(path: Path, *, name: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete {name} result: {path}")
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError(f"{name} must not use historical detector artifacts")
    return dict(payload)


def _require_current_homr_bundle(payload: Mapping[str, Any]) -> dict[str, Path]:
    """Validate the current-HOMR artifacts owned by canonical x4 support."""

    if payload.get("connector_complete") is not True:
        raise RuntimeError("Current x4 support requires a complete connector semantic pair")

    required_fields = (
        "current_sr_detection",
        "staff_mask",
        "connector_symbols",
        "connector_brace_dot",
    )
    missing_fields = [name for name in required_fields if not payload.get(name)]
    if missing_fields:
        raise ValueError(
            "Current x4 support result lacks required HOMR artifacts: " + ", ".join(missing_fields)
        )

    paths = {name: Path(str(payload[name])).resolve() for name in required_fields}
    missing_files = [str(path) for path in paths.values() if not path.is_file()]
    if missing_files:
        raise FileNotFoundError(
            "Current x4 support HOMR artifacts missing: " + ", ".join(missing_files)
        )
    return paths


def _require_precomputed_sr(
    request: Mapping[str, Any], *, image: Path
) -> dict[str, Any] | None:
    raw = request.get("precomputed_sr")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("precomputed_sr must be a mapping")
    if raw.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("Precomputed current x4 SR must not use historical artifacts")

    payload_image = Path(str(raw.get("image", ""))).resolve()
    if payload_image != image:
        raise ValueError(
            f"Precomputed current x4 SR image mismatch: expected={image}, actual={payload_image}"
        )
    if int(raw.get("sr_scale", 0)) != 4:
        raise ValueError("Precomputed current x4 SR requires sr_scale=4")

    sr_image = Path(str(raw.get("sr_image", ""))).resolve()
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)
    sr_sha256 = str(raw.get("sr_sha256", "")).strip()
    if not sr_sha256:
        raise ValueError("Precomputed current x4 SR lacks sr_sha256")

    return {
        "schema_version": "pipeline.current_x4_sr.v1",
        "status": "completed",
        "image": str(image),
        "sr_scale": 4,
        "sr_image": str(sr_image),
        "sr_sha256": sr_sha256,
        "historical_detector_artifact_runtime_input": False,
    }


def _build_worker_environment(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the fresh current-runtime environment without local HOMR shadow paths."""
    env = dict(os.environ if base_env is None else base_env)
    forbidden = {
        (PROJECT_ROOT / "homr").resolve(),
        (PROJECT_ROOT / "external" / "homr").resolve(),
        Path("/opt/homr_stage_e_profile").resolve(),
        Path("/opt/pdfscore_stage_e_profile").resolve(),
        Path("/opt/pdfscore_stage_e_profile/src").resolve(),
    }
    retained: list[str] = []
    for entry in env.get("PYTHONPATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
        except OSError:
            resolved = Path(entry)
        if resolved in forbidden or resolved == PROJECT_ROOT.resolve():
            continue
        retained.append(entry)

    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), *retained])
    return env


def _run_child_worker(
    *,
    name: str,
    module: str,
    request: Mapping[str, Any],
    request_path: Path,
    result_path: Path,
    log_path: Path,
    python_step: str,
    env: Mapping[str, str],
) -> tuple[dict[str, Any], list[str]]:
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(dict(request), indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    command = get_pipeline_python(python_step) + [
        "-m",
        module,
        "--request",
        str(request_path),
        "--result",
        str(result_path),
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=dict(env),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if process.returncode != 0:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = "\n".join(lines[-60:])
        raise RuntimeError(
            f"{name} failed ({process.returncode}): {request.get('image')}\n"
            f"--- worker log tail ---\n{tail}"
        )
    return _load_completed_result(result_path, name=name), command


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-support request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    output_root = Path(str(request["output_root"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    set_context(page=image.name)

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current support requires sr_scale=4, got {sr_scale}")

    env = _build_worker_environment()

    stem = image.stem
    sr_image = output_root / "sr" / "batch" / stem / image.name
    precomputed_sr = _require_precomputed_sr(request, image=image)
    if precomputed_sr is None:
        with span("current_support.current_sr_subprocess"):
            sr_payload, sr_command = _run_child_worker(
                name="Current x4 SR",
                module="src.pipeline.detection.current_sr_worker",
                request={
                    "schema_version": "pipeline.current_x4_sr_request.v1",
                    "detection": dict(det_cfg),
                    "image": str(image),
                    "output": str(sr_image),
                },
                request_path=output_root / "current_sr_request.json",
                result_path=output_root / "current_sr_result.json",
                log_path=output_root / "current_sr_worker.log",
                python_step="sr",
                env=env,
            )
        sr_execution_scope = "page_subprocess"
        memory_phase_boundaries = ["sr", "current_homr", "omr_dln"]
    else:
        sr_payload = precomputed_sr
        sr_command = ["precomputed-current-x4-sr", str(sr_payload["sr_image"])]
        sr_execution_scope = "dedicated_sr_batch_process"
        memory_phase_boundaries = ["sr_batch_process_exited", "current_homr", "omr_dln"]

    actual_sr = Path(str(sr_payload["sr_image"])).resolve()
    if precomputed_sr is None and actual_sr != sr_image.resolve():
        raise FileNotFoundError(f"Current x4 SR output mismatch: {actual_sr}")
    if not actual_sr.is_file():
        raise FileNotFoundError(actual_sr)

    current_homr_root = output_root / "current_homr"
    homr_payload, homr_command = _run_child_worker(
        name="Current HOMR on x4",
        module="src.pipeline.detection.current_homr_worker",
        request={
            "schema_version": "pipeline.current_homr_on_x4_request.v1",
            "detection": dict(det_cfg),
            "image": str(image),
            "sr_image": str(actual_sr),
            "output_root": str(current_homr_root),
        },
        request_path=output_root / "current_homr_request.json",
        result_path=output_root / "current_homr_result.json",
        log_path=output_root / "current_homr_worker.log",
        python_step="homr",
        env=env,
    )
    homr_paths = _require_current_homr_bundle(homr_payload)

    omr_output = output_root / "omr_sr"
    # The batch worker writes the same stable per-page SR layout used by the old
    # page-local SR worker, so OMR-DLN keeps consuming its existing persisted path.
    sr_directory = actual_sr.parent.parent
    omr_cmd = get_pipeline_python("omr_dln") + [
        "experiments/models/eval_omr_dln.py",
        "--images",
        str(image),
        "--output-dir",
        str(omr_output),
        "--pre-computed-sr",
        str(sr_directory),
    ]
    run_with_logging(omr_cmd, env=env, check=True)

    omr_predictions = omr_output / stem / "predictions.json"
    if not omr_predictions.is_file():
        raise FileNotFoundError(omr_predictions)

    payload = {
        "schema_version": "pipeline.current_x4_support.v3",
        "status": "completed",
        "image": str(image),
        "sr_scale": 4,
        "sr_image": str(actual_sr),
        "sr_sha256": sr_payload.get("sr_sha256"),
        "sr_execution_scope": sr_execution_scope,
        "current_sr_detection": str(homr_paths["current_sr_detection"]),
        "current_homr_staff_mask": str(homr_paths["staff_mask"]),
        "connector_complete": True,
        "connector_symbols": str(homr_paths["connector_symbols"]),
        "connector_brace_dot": str(homr_paths["connector_brace_dot"]),
        "homr_api_compat": homr_payload.get("homr_api_compat"),
        "current_omr": str(omr_predictions),
        "support_root": str(output_root),
        "current_homr_executed": True,
        "memory_phase_boundaries": memory_phase_boundaries,
        "historical_detector_artifact_runtime_input": False,
        "commands": [sr_command, homr_command, omr_cmd],
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    set_context(process_role="current_support_worker")
    try:
        result = run(args.request, args.result)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", "result": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
