"""Run the focused downstream propagation gate for Issue #284 channels-last SR.

The SR candidate is materialized in a disposable CUDA process. Only after that
process exits do current HOMR and OMR-DLN run, preserving the production memory
boundary. The runner compares the candidate's current-HOMR detections, staff and
connector masks, OMR predictions, and hybrid consensus with the retained
post-#285 baseline for page_013.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import yaml

from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from tools.issue284.profile_realesrgan_hotpath import sha256

PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_command(
    *, name: str, command: list[str], log_path: Path, env: dict[str, str]
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    wall = time.perf_counter() - started
    result = {
        "name": name,
        "command": command,
        "returncode": process.returncode,
        "wall_sec": wall,
        "log": str(log_path),
    }
    if process.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        raise RuntimeError(f"{name} failed ({process.returncode})\n" + "\n".join(tail))
    return result


def _select_baseline_sr(summary: dict[str, Any], image: Path) -> Path:
    candidates = []
    for item in summary.get("sr_outputs", []):
        if Path(str(item.get("image", ""))).name != image.name:
            continue
        sr_image = Path(str(item.get("sr_image", ""))).resolve()
        if sr_image.is_file():
            candidates.append(sr_image)
    preferred = [path for path in candidates if "one_page_trace_off" in path.parts]
    if preferred:
        return preferred[0]
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No retained baseline SR for {image.name}")


def _find_support_root(sr_image: Path) -> Path:
    for parent in sr_image.parents:
        if parent.name == "artifacts":
            return parent
    raise FileNotFoundError(f"Could not resolve support root from {sr_image}")


def _find_hybrid_run_root(sr_image: Path, stem: str) -> Path:
    relative = Path("baseline") / "batch" / stem / f"{stem}_detections.json"
    for parent in sr_image.parents:
        if (parent / relative).is_file():
            return parent
    raise FileNotFoundError(f"Could not resolve hybrid run root from {sr_image}")


def _detection_config(summary: dict[str, Any]) -> dict[str, Any]:
    for workload in summary.get("workloads", []):
        if workload.get("name") != "one_page_trace_off":
            continue
        config_path = Path(str(workload["config"])).resolve()
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        detection = config.get("detection")
        if not isinstance(detection, dict):
            raise ValueError(f"Baseline config lacks detection mapping: {config_path}")
        return detection
    raise ValueError("Baseline summary lacks one_page_trace_off workload")


def _compare_json(candidate: Path, reference: Path) -> dict[str, Any]:
    candidate_payload = _load_json(candidate)
    reference_payload = _load_json(reference)
    result: dict[str, Any] = {
        "candidate": str(candidate),
        "reference": str(reference),
        "candidate_sha256": sha256(candidate),
        "reference_sha256": sha256(reference),
        "sha256_equal": sha256(candidate) == sha256(reference),
        "parsed_equal": candidate_payload == reference_payload,
        "candidate_type": type(candidate_payload).__name__,
        "reference_type": type(reference_payload).__name__,
    }
    if isinstance(candidate_payload, list) and isinstance(reference_payload, list):
        result["candidate_count"] = len(candidate_payload)
        result["reference_count"] = len(reference_payload)
        result["different_items_same_index"] = sum(
            left != right for left, right in zip(candidate_payload, reference_payload)
        ) + abs(len(candidate_payload) - len(reference_payload))
    return result


def _compare_image(candidate: Path, reference: Path) -> dict[str, Any]:
    candidate_image = cv2.imread(str(candidate), cv2.IMREAD_UNCHANGED)
    reference_image = cv2.imread(str(reference), cv2.IMREAD_UNCHANGED)
    if candidate_image is None:
        raise FileNotFoundError(candidate)
    if reference_image is None:
        raise FileNotFoundError(reference)
    same_shape = candidate_image.shape == reference_image.shape
    result: dict[str, Any] = {
        "candidate": str(candidate),
        "reference": str(reference),
        "same_shape": same_shape,
        "candidate_shape": list(candidate_image.shape),
        "reference_shape": list(reference_image.shape),
        "array_equal": False,
    }
    if not same_shape:
        return result
    delta = np.abs(candidate_image.astype(np.int32) - reference_image.astype(np.int32))
    result.update(
        {
            "array_equal": bool(np.array_equal(candidate_image, reference_image)),
            "different_values": int(np.count_nonzero(delta)),
            "max_abs_diff": int(delta.max()) if delta.size else 0,
            "mean_abs_diff": float(delta.mean()) if delta.size else 0.0,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, default=IMAGE)
    args = parser.parse_args()

    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 downstream gate requires canonical /workspace container")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)

    baseline_summary_path = args.baseline_summary.resolve()
    summary = _load_json(baseline_summary_path)
    image = args.image.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = image.stem

    baseline_sr = _select_baseline_sr(summary, image)
    baseline_support = _find_support_root(baseline_sr)
    baseline_homr_result_path = baseline_support / "current_homr_result.json"
    baseline_homr = _load_json(baseline_homr_result_path)
    baseline_run_root = _find_hybrid_run_root(baseline_sr, stem)
    baseline_original_detection = (
        baseline_run_root / "baseline" / "batch" / stem / f"{stem}_detections.json"
    )
    baseline_omr = baseline_support / "omr_sr" / stem / "predictions.json"
    baseline_hybrid = baseline_run_root / "hybrid_results" / f"{stem}_hybrid.json"
    detection = _detection_config(summary)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).strip(
        os.pathsep
    )

    payload: dict[str, Any] = {
        "schema_version": "issue284.channels_last_downstream_gate.v1",
        "status": "started",
        "image": str(image),
        "baseline_summary": str(baseline_summary_path),
        "baseline_sr": str(baseline_sr),
        "baseline_support_root": str(baseline_support),
        "baseline_hybrid_run_root": str(baseline_run_root),
        "candidate": {
            "tile": 400,
            "tile_pad": 10,
            "channels_last": True,
            "benchmark": False,
            "output_mode": "gpu_uint8_cpu_stitch",
        },
        "commands": [],
    }
    result_path = output / "channels_last_downstream_gate.json"

    try:
        candidate_sr_dir = output / "candidate_sr"
        candidate_sr = candidate_sr_dir / image.name
        materialize_result = output / "materialize_result.json"
        materialize_cmd = [
            str(PIPELINE_PYTHON),
            "tools/issue284/materialize_sr_stitch_candidate.py",
            "--image",
            str(image),
            "--output-image",
            str(candidate_sr),
            "--result",
            str(materialize_result),
            "--tile",
            "400",
            "--tile-pad",
            "10",
            "--channels-last",
        ]
        payload["commands"].append(
            _run_command(
                name="materialize_channels_last_sr",
                command=materialize_cmd,
                log_path=output / "materialize.console.log",
                env=env,
            )
        )
        payload["materialize"] = _load_json(materialize_result)
        payload["sr_comparison"] = _compare_image(candidate_sr, baseline_sr)

        homr_root = output / "candidate_current_homr"
        homr_request = output / "current_homr_request.json"
        homr_result = output / "current_homr_result.json"
        homr_request.write_text(
            json.dumps(
                {
                    "schema_version": "pipeline.current_homr_on_x4_request.v1",
                    "detection": detection,
                    "image": str(image),
                    "sr_image": str(candidate_sr),
                    "output_root": str(homr_root),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        homr_cmd = [
            str(PIPELINE_PYTHON),
            "-m",
            "src.pipeline.detection.current_homr_worker",
            "--request",
            str(homr_request),
            "--result",
            str(homr_result),
        ]
        payload["commands"].append(
            _run_command(
                name="current_homr_on_candidate_sr",
                command=homr_cmd,
                log_path=output / "current_homr.console.log",
                env=env,
            )
        )
        candidate_homr = _load_json(homr_result)
        if candidate_homr.get("status") != "completed":
            raise ValueError(f"Incomplete candidate HOMR result: {homr_result}")

        omr_root = output / "candidate_omr"
        omr_cmd = [
            str(PIPELINE_PYTHON),
            "experiments/models/eval_omr_dln.py",
            "--images",
            str(image),
            "--output-dir",
            str(omr_root),
            "--pre-computed-sr",
            str(candidate_sr_dir),
        ]
        payload["commands"].append(
            _run_command(
                name="omr_dln_on_candidate_sr",
                command=omr_cmd,
                log_path=output / "omr_dln.console.log",
                env=env,
            )
        )
        candidate_omr = omr_root / stem / "predictions.json"
        if not candidate_omr.is_file():
            raise FileNotFoundError(candidate_omr)

        artifact_fields = (
            "current_sr_detection",
            "staff_mask",
            "connector_symbols",
            "connector_brace_dot",
        )
        artifact_comparisons: dict[str, Any] = {}
        for field in artifact_fields:
            candidate_value = candidate_homr.get(field)
            reference_value = baseline_homr.get(field)
            if not candidate_value or not reference_value:
                artifact_comparisons[field] = {
                    "available": False,
                    "candidate": candidate_value,
                    "reference": reference_value,
                }
                continue
            candidate_path = Path(str(candidate_value)).resolve()
            reference_path = Path(str(reference_value)).resolve()
            if field == "current_sr_detection":
                artifact_comparisons[field] = _compare_json(candidate_path, reference_path)
            else:
                artifact_comparisons[field] = _compare_image(candidate_path, reference_path)
        payload["current_homr_artifacts"] = artifact_comparisons
        payload["omr_predictions"] = _compare_json(candidate_omr, baseline_omr)

        candidate_hybrid_payload = apply_hybrid_consensus_filter(
            baseline_boxes=load_json_boxes(baseline_original_detection),
            sr_boxes=load_json_boxes(Path(str(candidate_homr["current_sr_detection"]))),
            omr_boxes=load_json_boxes(candidate_omr),
        )
        candidate_hybrid = output / "candidate_hybrid.json"
        candidate_hybrid.write_text(
            json.dumps(candidate_hybrid_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        payload["hybrid_consensus"] = _compare_json(candidate_hybrid, baseline_hybrid)

        homr_equal = all(
            (
                item.get("parsed_equal")
                if field == "current_sr_detection"
                else item.get("array_equal")
            )
            for field, item in artifact_comparisons.items()
            if item.get("available", True)
        ) and all(item.get("available", True) for item in artifact_comparisons.values())
        omr_equal = bool(payload["omr_predictions"].get("parsed_equal"))
        hybrid_equal = bool(payload["hybrid_consensus"].get("parsed_equal"))
        payload.update(
            {
                "status": "completed",
                "all_current_homr_artifacts_equal": homr_equal,
                "omr_predictions_equal": omr_equal,
                "hybrid_consensus_equal": hybrid_equal,
                "all_focused_downstream_equal": homr_equal and omr_equal and hybrid_equal,
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
