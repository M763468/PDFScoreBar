"""Compare eager and torch.compile SR outputs through focused downstream consumers.

This gate reuses already-materialized x4 SR PNGs. It runs current HOMR and OMR-DLN
once for each SR input, then compares the downstream artifacts directly. If the
current-SR detection and OMR predictions are equal, hybrid consensus is also
unchanged for the same baseline detections because those are its only varying
SR-side inputs.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from tools.issue284.run_channels_last_downstream_gate import (
    PIPELINE_PYTHON,
    ROOT,
    _compare_image,
    _compare_json,
    _load_json,
    _run_command,
)

DEFAULT_IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
DEFAULT_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"


def _detection_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    detection = payload.get("detection") if isinstance(payload, dict) else None
    if not isinstance(detection, dict):
        raise ValueError(f"Config lacks detection mapping: {path}")
    return dict(detection)


def _run_homr(
    *,
    label: str,
    image: Path,
    sr_image: Path,
    detection: dict[str, Any],
    output: Path,
    env: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = output / f"{label}_current_homr"
    request = output / f"{label}_current_homr_request.json"
    result = output / f"{label}_current_homr_result.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.current_homr_on_x4_request.v1",
                "detection": detection,
                "image": str(image),
                "sr_image": str(sr_image),
                "output_root": str(root),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.detection.current_homr_worker",
        "--request",
        str(request),
        "--result",
        str(result),
    ]
    command_result = _run_command(
        name=f"current_homr_{label}",
        command=command,
        log_path=output / f"{label}_current_homr.console.log",
        env=env,
    )
    payload = _load_json(result)
    if payload.get("status") != "completed":
        raise ValueError(f"Incomplete {label} HOMR result: {result}")
    return payload, command_result


def _run_omr(
    *,
    label: str,
    image: Path,
    sr_image: Path,
    output: Path,
    env: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    root = output / f"{label}_omr"
    command = [
        str(PIPELINE_PYTHON),
        "experiments/models/eval_omr_dln.py",
        "--images",
        str(image),
        "--output-dir",
        str(root),
        "--pre-computed-sr",
        str(sr_image.parent),
    ]
    command_result = _run_command(
        name=f"omr_dln_{label}",
        command=command,
        log_path=output / f"{label}_omr.console.log",
        env=env,
    )
    predictions = root / image.stem / "predictions.json"
    if not predictions.is_file():
        raise FileNotFoundError(predictions)
    return predictions, command_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--eager-sr", type=Path, required=True)
    parser.add_argument("--compiled-sr", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 compile downstream gate requires canonical /workspace container")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)

    image = args.image.resolve()
    eager_sr = args.eager_sr.resolve()
    compiled_sr = args.compiled_sr.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "compile_pair_downstream_gate.json"

    for path in (image, eager_sr, compiled_sr, config):
        if not path.is_file():
            raise FileNotFoundError(path)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    detection = _detection_config(config)

    payload: dict[str, Any] = {
        "schema_version": "issue284.compile_pair_downstream_gate.v1",
        "status": "started",
        "image": str(image),
        "eager_sr": str(eager_sr),
        "compiled_sr": str(compiled_sr),
        "config": str(config),
        "commands": [],
    }

    try:
        payload["sr_comparison"] = _compare_image(compiled_sr, eager_sr)

        eager_homr, eager_homr_command = _run_homr(
            label="eager",
            image=image,
            sr_image=eager_sr,
            detection=detection,
            output=output,
            env=env,
        )
        payload["commands"].append(eager_homr_command)
        compiled_homr, compiled_homr_command = _run_homr(
            label="compiled",
            image=image,
            sr_image=compiled_sr,
            detection=detection,
            output=output,
            env=env,
        )
        payload["commands"].append(compiled_homr_command)

        artifact_fields = (
            "current_sr_detection",
            "staff_mask",
            "connector_symbols",
            "connector_brace_dot",
        )
        artifact_comparisons: dict[str, Any] = {}
        for field in artifact_fields:
            eager_value = eager_homr.get(field)
            compiled_value = compiled_homr.get(field)
            if not eager_value or not compiled_value:
                artifact_comparisons[field] = {
                    "available": False,
                    "eager": eager_value,
                    "compiled": compiled_value,
                }
                continue
            eager_path = Path(str(eager_value)).resolve()
            compiled_path = Path(str(compiled_value)).resolve()
            if field == "current_sr_detection":
                artifact_comparisons[field] = _compare_json(compiled_path, eager_path)
            else:
                artifact_comparisons[field] = _compare_image(compiled_path, eager_path)
        payload["current_homr_artifacts"] = artifact_comparisons

        eager_omr, eager_omr_command = _run_omr(
            label="eager",
            image=image,
            sr_image=eager_sr,
            output=output,
            env=env,
        )
        payload["commands"].append(eager_omr_command)
        compiled_omr, compiled_omr_command = _run_omr(
            label="compiled",
            image=image,
            sr_image=compiled_sr,
            output=output,
            env=env,
        )
        payload["commands"].append(compiled_omr_command)
        payload["omr_predictions"] = _compare_json(compiled_omr, eager_omr)

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
        hybrid_inputs_equal = bool(
            artifact_comparisons.get("current_sr_detection", {}).get("parsed_equal") and omr_equal
        )
        payload.update(
            {
                "status": "completed",
                "all_current_homr_artifacts_equal": homr_equal,
                "omr_predictions_equal": omr_equal,
                "hybrid_sr_side_inputs_equal": hybrid_inputs_equal,
                "all_focused_downstream_equal": homr_equal and omr_equal,
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
    return 0 if payload["all_focused_downstream_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
