"""Compare eager and torch.compile SR outputs through focused downstream consumers.

This gate reuses already-materialized x4 SR PNGs. It runs current HOMR and OMR-DLN
once for each SR input, compares normalized source-coordinate box sets, runs the
verified Stage E baseline HOMR once, and then compares the actual hybrid consensus
produced from the eager and compiled SR-side inputs.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from src.common import barline_iou
from src.pipeline.detection.homr_profile import (
    build_profile_command,
    build_profile_environment,
    load_homr_profile,
    validate_profile_runtime,
)
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
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
VERIFIED_PROFILE = "stage_e_verified"


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


def _run_verified_baseline(*, image: Path, output: Path) -> tuple[Path, dict[str, Any]]:
    profile = load_homr_profile(VERIFIED_PROFILE)
    validate_profile_runtime(profile)
    root = output / "verified_baseline"
    root.mkdir(parents=True, exist_ok=True)
    command = build_profile_command(profile, images=[image], output_root=root)
    command_result = _run_command(
        name="verified_stage_e_baseline",
        command=command,
        log_path=output / "verified_baseline.console.log",
        env=build_profile_environment(profile),
    )
    detections = root / "batch" / image.stem / f"{image.stem}_detections.json"
    if not detections.is_file():
        raise FileNotFoundError(detections)
    return detections, command_result


def _box_set_comparison(candidate: Path, reference: Path) -> dict[str, Any]:
    candidate_boxes = load_json_boxes(candidate)
    reference_boxes = load_json_boxes(reference)
    candidate_set = set(candidate_boxes)
    reference_set = set(reference_boxes)

    def best_iou(box: tuple[int, int, int, int], others: list[tuple[int, int, int, int]]) -> float:
        if not others:
            return 0.0
        return max(float(barline_iou(box, other)) for other in others)

    candidate_best = [best_iou(box, reference_boxes) for box in candidate_boxes]
    reference_best = [best_iou(box, candidate_boxes) for box in reference_boxes]
    candidate_only = [list(box) for box in candidate_boxes if box not in reference_set]
    reference_only = [list(box) for box in reference_boxes if box not in candidate_set]

    return {
        "candidate_count": len(candidate_boxes),
        "reference_count": len(reference_boxes),
        "ordered_equal": candidate_boxes == reference_boxes,
        "set_equal": candidate_set == reference_set,
        "exact_shared_count": len(candidate_set & reference_set),
        "candidate_only_count": len(candidate_only),
        "reference_only_count": len(reference_only),
        "candidate_only_boxes": candidate_only[:20],
        "reference_only_boxes": reference_only[:20],
        "candidate_min_best_iou": min(candidate_best) if candidate_best else None,
        "reference_min_best_iou": min(reference_best) if reference_best else None,
        "candidate_unmatched_iou_gt_0_5": sum(value <= 0.5 for value in candidate_best),
        "reference_unmatched_iou_gt_0_5": sum(value <= 0.5 for value in reference_best),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--eager-sr", type=Path, required=True)
    parser.add_argument("--compiled-sr", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(
            "Issue #284 compile downstream gate requires canonical /workspace container"
        )
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
        "schema_version": "issue284.compile_pair_downstream_gate.v2",
        "status": "started",
        "image": str(image),
        "eager_sr": str(eager_sr),
        "compiled_sr": str(compiled_sr),
        "config": str(config),
        "verified_baseline_profile": VERIFIED_PROFILE,
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

        eager_detection = Path(str(eager_homr["current_sr_detection"])).resolve()
        compiled_detection = Path(str(compiled_homr["current_sr_detection"])).resolve()
        payload["current_homr_boxes"] = _box_set_comparison(compiled_detection, eager_detection)

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
        payload["omr_boxes"] = _box_set_comparison(compiled_omr, eager_omr)

        baseline_detection, baseline_command = _run_verified_baseline(image=image, output=output)
        payload["commands"].append(baseline_command)
        baseline_boxes = load_json_boxes(baseline_detection)
        eager_hybrid = apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=load_json_boxes(eager_detection),
            omr_boxes=load_json_boxes(eager_omr),
        )
        compiled_hybrid = apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=load_json_boxes(compiled_detection),
            omr_boxes=load_json_boxes(compiled_omr),
        )
        eager_set = {tuple(box) for box in eager_hybrid}
        compiled_set = {tuple(box) for box in compiled_hybrid}
        payload["hybrid_consensus"] = {
            "baseline_count": len(baseline_boxes),
            "eager_count": len(eager_hybrid),
            "compiled_count": len(compiled_hybrid),
            "ordered_equal": eager_hybrid == compiled_hybrid,
            "set_equal": eager_set == compiled_set,
            "eager_only": [list(box) for box in sorted(eager_set - compiled_set)],
            "compiled_only": [list(box) for box in sorted(compiled_set - eager_set)],
        }

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
        hybrid_equal = bool(payload["hybrid_consensus"]["ordered_equal"])
        payload.update(
            {
                "status": "completed",
                "strict_current_homr_artifacts_equal": homr_equal,
                "strict_omr_predictions_equal": omr_equal,
                "strict_intermediate_equal": homr_equal and omr_equal,
                "focused_hybrid_consensus_equal": hybrid_equal,
                "focused_consensus_gate_passed": hybrid_equal,
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
    return 0 if payload["focused_consensus_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
