#!/usr/bin/env python3
"""Evaluate a frozen-logit fusion head from retained Issue #332 outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.dual_view_diagnosis import (
    _by_score,
    _crossings,
    _metrics,
    _probability_envelope,
)
from tools.mmr_training.issue332.dual_view_fusion import (
    MonotonicLogitFusion,
    fuse_probabilities,
    sha256_file,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(row: dict[str, Any]) -> tuple[str, str, float, str]:
    return (
        str(row["sample_id"]),
        str(row["variant"]),
        float(row.get("dpi_scale", 1.0)),
        str(row.get("resize_mode", "direct")),
    )


def _load_fusion(path: Path) -> tuple[list[float], float, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = payload["fusion_state_dict"]
    model = MonotonicLogitFusion()
    model.load_state_dict(state)
    weights = [float(value) for value in model.effective_weights().detach()]
    bias = float(model.bias.detach())
    return weights, bias, payload


def _aligned_measure_rows(
    full_path: Path, staff_path: Path, *, weights: Sequence[float], bias: float
) -> list[dict[str, Any]]:
    full_rows = {_key(row): row for row in _load_json(full_path)["rows"]}
    staff_rows = {_key(row): row for row in _load_json(staff_path)["rows"]}
    if set(full_rows) != set(staff_rows):
        raise ValueError("full/staff benchmark rows do not align")
    rows = []
    for key in sorted(full_rows):
        full = full_rows[key]
        staff = staff_rows[key]
        if int(full["label"]) != int(staff["label"]):
            raise ValueError(f"label mismatch for {key}")
        probability = fuse_probabilities(
            float(full["probability"]),
            float(staff["probability"]),
            weights=weights,
            bias=bias,
        )
        rows.append(
            {
                "sample_id": full["sample_id"],
                "score_id": full["score_id"],
                "page_id": full["page_id"],
                "label": int(full["label"]),
                "tags": full.get("tags", []),
                "variant": full["variant"],
                "dpi_scale": float(full.get("dpi_scale", 1.0)),
                "resize_mode": full.get("resize_mode", "direct"),
                "full_probability": float(full["probability"]),
                "staff_probability": float(staff["probability"]),
                "fusion_probability": probability,
            }
        )
    return rows


def _native(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["variant"] == "native"
        and float(row.get("dpi_scale", 1.0)) == 1.0
        and row.get("resize_mode", "direct") == "direct"
    ]


def _view_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    native = _native(rows)
    return {
        "native": _metrics(native, "fusion_probability"),
        "per_score_native": _by_score(native, "fusion_probability"),
        "geometry": {
            "main": _crossings(rows, "fusion_probability", threshold=0.5),
            "rescue": _crossings(rows, "fusion_probability", threshold=0.1),
            "probability_envelope": _probability_envelope(rows, "fusion_probability"),
        },
    }


def _staff_geometry_rows(
    measure_rows: Sequence[dict[str, Any]],
    staff_rows: Sequence[dict[str, Any]],
    *,
    weights: Sequence[float],
    bias: float,
) -> list[dict[str, Any]]:
    full_native = {row["sample_id"]: row for row in _native(measure_rows)}
    result = []
    for staff in staff_rows:
        full = full_native[str(staff["sample_id"])]
        result.append(
            {
                "sample_id": staff["sample_id"],
                "score_id": staff["score_id"],
                "page_id": staff["page_id"],
                "label": int(staff["label"]),
                "variant": staff["variant"],
                "dpi_scale": 1.0,
                "resize_mode": "direct",
                "full_probability": float(full["full_probability"]),
                "staff_probability": float(staff["probability"]),
                "fusion_probability": fuse_probabilities(
                    float(full["full_probability"]),
                    float(staff["probability"]),
                    weights=weights,
                    bias=bias,
                ),
            }
        )
    return result


def _false_positive_guard(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    false_positives = [
        row
        for row in _native(rows)
        if int(row["label"]) == 0 and float(row["fusion_probability"]) >= 0.5
    ]
    tagged = [
        row
        for row in false_positives
        if set(row.get("tags", [])) & {"negative", "zero-fixture", "one-bar"}
    ]
    return {
        "native_false_positive_count": len(false_positives),
        "negative_zero_fixture_one_bar_false_positive_count": len(tagged),
        "false_positive_sample_ids": sorted(row["sample_id"] for row in false_positives),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    weights, bias, model_payload = _load_fusion(args.fusion_model)
    diagnosis = _load_json(args.staff_diagnosis)
    primary_rows = _aligned_measure_rows(
        args.full_primary, args.staff_primary, weights=weights, bias=bias
    )
    controls_rows = _aligned_measure_rows(
        args.full_controls, args.staff_controls, weights=weights, bias=bias
    )
    primary_staff_rows = _staff_geometry_rows(
        primary_rows,
        diagnosis["staff_bbox_sensitivity"]["primary"]["rows"],
        weights=weights,
        bias=bias,
    )
    controls_staff_rows = _staff_geometry_rows(
        controls_rows,
        diagnosis["staff_bbox_sensitivity"]["controls"]["rows"],
        weights=weights,
        bias=bias,
    )
    full_runtime = _load_json(args.full_primary)["summary"]["direct"]["mean_inference_ms"]
    staff_runtime = _load_json(args.staff_primary)["summary"]["direct"]["mean_inference_ms"]
    output = {
        "provenance": {
            "fusion_model": str(args.fusion_model.resolve()),
            "fusion_model_sha256": sha256_file(args.fusion_model),
            "full_primary": str(args.full_primary.resolve()),
            "staff_primary": str(args.staff_primary.resolve()),
            "full_controls": str(args.full_controls.resolve()),
            "staff_controls": str(args.staff_controls.resolve()),
            "staff_diagnosis": str(args.staff_diagnosis.resolve()),
            "source_full_model_sha256": model_payload["full_model_sha256"],
            "source_staff_model_sha256": model_payload["staff_model_sha256"],
            "retained_outputs_reused": True,
        },
        "contract": {
            "weights": weights,
            "bias": bias,
            "main_threshold": 0.5,
            "rescue_threshold": 0.1,
            "staff_bbox_perturbation": "independent +/-1/2/4px translate/top/bottom/height",
        },
        "primary": {
            "summary": _view_summary(primary_rows),
            "false_positive_guard": _false_positive_guard(primary_rows),
            "rows": primary_rows,
        },
        "controls": {
            "summary": _view_summary(controls_rows),
            "false_positive_guard": _false_positive_guard(controls_rows),
            "rows": controls_rows,
        },
        "staff_bbox_sensitivity": {
            "primary": {"summary": _view_summary(primary_staff_rows), "rows": primary_staff_rows},
            "controls": {
                "summary": _view_summary(controls_staff_rows),
                "rows": controls_staff_rows,
            },
        },
        "runtime": {
            "full_mean_inference_ms": full_runtime,
            "staff_mean_inference_ms": staff_runtime,
            "estimated_serial_dual_view_ms": full_runtime + staff_runtime,
            "fusion_head_cost": "negligible convex mixture plus bias",
            "parameter_count": "two ResNet18 encoders plus 2 fusion scalars",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fusion-model", type=Path, required=True)
    parser.add_argument("--full-primary", type=Path, required=True)
    parser.add_argument("--staff-primary", type=Path, required=True)
    parser.add_argument("--full-controls", type=Path, required=True)
    parser.add_argument("--staff-controls", type=Path, required=True)
    parser.add_argument("--staff-diagnosis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "primary": result["primary"]["summary"],
                "controls": result["controls"]["summary"],
                "staff_bbox_sensitivity": result["staff_bbox_sensitivity"]["primary"]["summary"][
                    "geometry"
                ],
                "runtime": result["runtime"],
            },
            indent=2,
        )
    )
