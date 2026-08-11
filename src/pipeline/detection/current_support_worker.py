"""Generate current x4 SR and OMR support for one detector page.

The restored Stage E hybrid consumes the verified HOMR baseline, verified HOMR on
the fresh x4 image, and current OMR-DLN evidence.  Current HOMR-on-x4 detections
are not part of that consensus, so this worker deliberately does not run them.
The memory-heavy SR process exits before OMR-DLN starts.
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


def _run_current_sr(
    *,
    det_cfg: Mapping[str, Any],
    image: Path,
    output_root: Path,
    env: Mapping[str, str],
) -> tuple[dict[str, Any], list[str]]:
    stem = image.stem
    sr_image = output_root / "sr" / "batch" / stem / image.name
    request_path = output_root / "current_sr_request.json"
    result_path = output_root / "current_sr_result.json"
    log_path = output_root / "current_sr_worker.log"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.current_x4_sr_request.v1",
                "detection": dict(det_cfg),
                "image": str(image),
                "output": str(sr_image),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    command = get_pipeline_python("sr") + [
        "-m",
        "src.pipeline.detection.current_sr_worker",
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
            f"Current x4 SR failed ({process.returncode}): {image}\n"
            f"--- SR worker log tail ---\n{tail}"
        )

    payload = _load_completed_result(result_path, name="current x4 SR")
    actual_sr = Path(str(payload["sr_image"])).resolve()
    if actual_sr != sr_image.resolve() or not actual_sr.is_file():
        raise FileNotFoundError(f"Current x4 SR output mismatch: {actual_sr}")
    return payload, command


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-support request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    output_root = Path(str(request["output_root"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current support requires sr_scale=4, got {sr_scale}")

    env = os.environ.copy()
    homr_path = PROJECT_ROOT / "external" / "homr"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT), str(homr_path), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    sr_payload, sr_command = _run_current_sr(
        det_cfg=det_cfg,
        image=image,
        output_root=output_root,
        env=env,
    )
    sr_image = Path(str(sr_payload["sr_image"])).resolve()

    stem = image.stem
    omr_output = output_root / "omr_sr"
    omr_cmd = get_pipeline_python("omr_dln") + [
        "experiments/models/eval_omr_dln.py",
        "--images",
        str(image),
        "--output-dir",
        str(omr_output),
        "--pre-computed-sr",
        str(output_root / "sr" / "batch"),
    ]
    run_with_logging(omr_cmd, cwd=PROJECT_ROOT, env=env, check=True)

    omr_predictions = omr_output / stem / "predictions.json"
    if not omr_predictions.is_file():
        raise FileNotFoundError(omr_predictions)

    payload = {
        "schema_version": "pipeline.current_x4_support.v2",
        "status": "completed",
        "image": str(image),
        "sr_scale": 4,
        "sr_image": str(sr_image),
        "sr_sha256": sr_payload.get("sr_sha256"),
        "current_omr": str(omr_predictions),
        "support_root": str(output_root),
        "current_homr_executed": False,
        "historical_detector_artifact_runtime_input": False,
        "commands": [sr_command, omr_cmd],
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
