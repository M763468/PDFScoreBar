#!/usr/bin/env python3
"""Compare Issue #294 same-original A/B artifacts and contract gates."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter

EXPECTED_HOMR_COMMIT = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
EXPECTED_MODEL_KEYS = {
    "segnet_fp16": "segnet",
    "transformer_encoder_fp16": "encoder",
    "transformer_decoder_fp16": "decoder",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Detection payload must be a mapping: {path}")
    predictions = payload.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError(f"Detection payload lacks predictions: {path}")
    boxes: list[tuple[int, int, int, int]] = []
    for item in predictions:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid prediction in {path}")
        bbox = item.get("orig_bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError(f"Invalid orig_bbox in {path}: {bbox!r}")
        boxes.append(tuple(int(value) for value in bbox))
    return boxes


def mask_iou(left: Path, right: Path) -> dict[str, Any]:
    left_mask = cv2.imread(str(left), cv2.IMREAD_GRAYSCALE)
    right_mask = cv2.imread(str(right), cv2.IMREAD_GRAYSCALE)
    if left_mask is None:
        raise FileNotFoundError(left)
    if right_mask is None:
        raise FileNotFoundError(right)
    shape_equal = left_mask.shape == right_mask.shape
    if not shape_equal:
        return {
            "shape_equal": False,
            "left_shape_hw": list(left_mask.shape),
            "right_shape_hw": list(right_mask.shape),
            "iou": None,
            "left_pixels": int((left_mask > 0).sum()),
            "right_pixels": int((right_mask > 0).sum()),
        }
    left_binary = left_mask > 0
    right_binary = right_mask > 0
    union = int((left_binary | right_binary).sum())
    intersection = int((left_binary & right_binary).sum())
    return {
        "shape_equal": True,
        "left_shape_hw": list(left_mask.shape),
        "right_shape_hw": list(right_mask.shape),
        "iou": intersection / union if union else 1.0,
        "intersection_pixels": intersection,
        "union_pixels": union,
        "left_pixels": int(left_binary.sum()),
        "right_pixels": int(right_binary.sum()),
    }


def box_comparison(
    left: list[tuple[int, int, int, int]],
    right: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    exact_intersection = left_counter & right_counter
    left_supported = apply_hybrid_consensus_filter(
        baseline_boxes=[list(box) for box in left],
        sr_boxes=[list(box) for box in right],
        omr_boxes=[],
    )
    right_supported = apply_hybrid_consensus_filter(
        baseline_boxes=[list(box) for box in right],
        sr_boxes=[list(box) for box in left],
        omr_boxes=[],
    )
    return {
        "left_count": len(left),
        "right_count": len(right),
        "ordered_equal": left == right,
        "multiset_equal": left_counter == right_counter,
        "exact_multiset_intersection_count": sum(exact_intersection.values()),
        "left_only_exact_count": sum((left_counter - right_counter).values()),
        "right_only_exact_count": sum((right_counter - left_counter).values()),
        "left_supported_by_right_iou_gt_0_5": len(left_supported),
        "right_supported_by_left_iou_gt_0_5": len(right_supported),
        "left_support_fraction": len(left_supported) / len(left) if left else 1.0,
        "right_support_fraction": len(right_supported) / len(right) if right else 1.0,
    }


def _session_role(model: object) -> str | None:
    name = Path(str(model)).name.lower()
    if "segnet" in name:
        return "segnet"
    if name.startswith("encoder_"):
        return "encoder"
    if name.startswith("decoder_"):
        return "decoder"
    return None


def maintained_runtime_contract(worker: dict[str, Any]) -> dict[str, Any]:
    runtime = worker.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    sessions = worker.get("onnx_sessions")
    if not isinstance(sessions, list):
        sessions = []

    role_sessions: dict[str, list[dict[str, Any]]] = {
        "segnet": [],
        "encoder": [],
        "decoder": [],
    }
    for item in sessions:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model", ""))
        if not model.endswith("_fp16.onnx"):
            continue
        role = _session_role(model)
        if role is not None:
            role_sessions[role].append(item)

    role_cuda_first = {
        role: bool(items)
        and all(
            isinstance(item.get("active_providers"), list)
            and bool(item["active_providers"])
            and item["active_providers"][0] == "CUDAExecutionProvider"
            for item in items
        )
        for role, items in role_sessions.items()
    }

    models = worker.get("models")
    if not isinstance(models, dict):
        models = {}
    model_hashes = {
        key: (
            value.get("sha256")
            if isinstance(value := models.get(key), dict) and value.get("exists") is True
            else None
        )
        for key in EXPECTED_MODEL_KEYS
    }
    model_hashes_captured = all(
        isinstance(value, str) and len(value) == 64 for value in model_hashes.values()
    )

    installed_commit = runtime.get("homr_installed_commit")
    coordinate_checks = worker.get("coordinate_checks")
    coordinate_ok = bool(
        isinstance(coordinate_checks, dict)
        and coordinate_checks.get("masks_match_original_shape") is True
    )
    artifacts = worker.get("artifacts")
    connector_ok = bool(
        isinstance(artifacts, dict) and artifacts.get("connector_complete") is True
    )
    all_fp16_cuda = all(role_cuda_first.values())
    return {
        "expected_homr_commit": EXPECTED_HOMR_COMMIT,
        "installed_homr_commit": installed_commit,
        "commit_verified": installed_commit == EXPECTED_HOMR_COMMIT,
        "fp16_session_count_by_role": {
            role: len(items) for role, items in role_sessions.items()
        },
        "fp16_cuda_first_provider_by_role": role_cuda_first,
        "all_required_fp16_roles_cuda_first": all_fp16_cuda,
        "model_sha256": model_hashes,
        "model_hashes_captured": model_hashes_captured,
        "coordinate_contract": coordinate_ok,
        "connector_complete": connector_ok,
        "hard_contract_pass": (
            installed_commit == EXPECTED_HOMR_COMMIT
            and all_fp16_cuda
            and model_hashes_captured
            and coordinate_ok
            and connector_ok
        ),
    }


def compare_page(page: dict[str, Any]) -> dict[str, Any]:
    a = page.get("A_pinned")
    b = page.get("B_maintained")
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("Page summary lacks A/B payloads")
    a_artifacts = a.get("artifacts")
    worker = b.get("worker")
    if not isinstance(a_artifacts, dict) or not isinstance(worker, dict):
        raise ValueError("Page summary lacks A/B artifact payloads")
    b_artifacts = worker.get("artifacts")
    if not isinstance(b_artifacts, dict):
        raise ValueError("Maintained worker lacks artifacts")

    a_detection = Path(str(a_artifacts["detections"]))
    b_detection = Path(str(b_artifacts["detections"]))
    a_boxes = load_boxes(a_detection)
    b_boxes = load_boxes(b_detection)

    return {
        "image": page.get("image"),
        "boxes": box_comparison(a_boxes, b_boxes),
        "staff_mask": mask_iou(
            Path(str(a_artifacts["staff_mask"])),
            Path(str(b_artifacts["staff_mask"])),
        ),
        "notehead_mask": mask_iou(
            Path(str(a_artifacts["notehead_mask"])),
            Path(str(b_artifacts["notehead_mask"])),
        ),
        "maintained_runtime_contract": maintained_runtime_contract(worker),
        "timing": page.get("timing"),
    }


def run(summary_path: Path, output: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    if not isinstance(summary, dict) or summary.get("status") != "completed":
        raise ValueError(f"Invalid A/B summary: {summary_path}")
    pages_payload = summary.get("pages")
    if not isinstance(pages_payload, list) or not pages_payload:
        raise ValueError("A/B summary has no pages")

    pages = [compare_page(page) for page in pages_payload if isinstance(page, dict)]
    if len(pages) != len(pages_payload):
        raise ValueError("A/B summary contains invalid page entries")
    aggregate_timing = summary.get("aggregate_timing")
    timing_gate = bool(
        isinstance(aggregate_timing, dict)
        and aggregate_timing.get("material_speed_gate_15pct") is True
    )
    hard_contracts = all(
        page["maintained_runtime_contract"]["hard_contract_pass"] for page in pages
    )
    report = {
        "schema_version": "issue294.same_original_comparison.v1",
        "status": "completed",
        "summary": str(summary_path.resolve()),
        "aggregate_timing": aggregate_timing,
        "pages": pages,
        "gates": {
            "material_speed_gate_15pct": timing_gate,
            "maintained_runtime_hard_contracts": hard_contracts,
            "eligible_for_geometry_review": timing_gate and hard_contracts,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.summary, args.output)
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
                "status": report["status"],
                "output": str(args.output.resolve()),
                "gates": report["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
