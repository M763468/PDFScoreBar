from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.pipeline.steps.candidate_filters import filter_probe_candidates
from tools.issue252.probe_boundary import (
    classify_first_loss,
    validate_fresh_contract_payload,
)
from tools.issue252.trace_prokofiev_probe_boundary import _apply_candidate_filter


def _source_trace(*, baseline: bool = True, hybrid: bool = False):
    return {
        "missing": {
            "fresh_baseline": {"accepted": baseline},
            "current_sr": {"accepted": False},
            "current_omr": {"accepted": False},
            "hybrid": {"accepted": hybrid},
        }
    }


def _target_stage(
    *,
    row=True,
    raw=False,
    size=False,
    heuristic=False,
    trimmed=False,
    final=False,
):
    return {
        "row_bands": [[1, 10]] if row else [],
        "raw": {"accepted": raw},
        "size_filtered": {"accepted": size},
        "heuristic_filtered": {"accepted": heuristic},
        "trimmed": {"accepted": trimmed},
        "final": {"accepted": final},
    }


def _variants(default, **extras):
    result = {"suppression_default": {"targets": {"missing": default}, "vertical_iou": 0.0}}
    for name, stage in extras.items():
        result[name] = {
            "targets": {"missing": stage},
            "vertical_iou": 0.1 if name != "suppression_off" else 0.0,
        }
    return result


def test_validate_fresh_contract_payload_accepts_direct_and_nested_contracts():
    contract = {
        "mode": "fresh_upstream",
        "fresh_upstream_authoritative": True,
        "override_keys": [],
    }
    assert validate_fresh_contract_payload(contract) == contract
    assert validate_fresh_contract_payload({"detector_input_contract": contract}) == contract


@pytest.mark.parametrize(
    "payload",
    [
        {
            "mode": "precomputed_candidate_route",
            "fresh_upstream_authoritative": False,
            "override_keys": ["cnn_bands_from"],
        },
        {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": False,
            "override_keys": [],
        },
        {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": ["precomputed_probe_candidates_root"],
        },
    ],
)
def test_validate_fresh_contract_payload_rejects_nonfresh_contract(payload):
    with pytest.raises(ValueError, match="not authoritative fresh upstream"):
        validate_fresh_contract_payload(payload)


def test_classifies_existing_box_suppression_when_off_variant_restores_raw_target():
    default = _target_stage(row=True, raw=False)
    restored = _target_stage(
        row=True,
        raw=True,
        size=True,
        heuristic=True,
        trimmed=True,
        final=True,
    )
    result = classify_first_loss(
        source_trace=_source_trace(),
        variants=_variants(default, suppression_off=restored),
    )
    assert result["boundary"] == "existing_box_suppression"
    assert result["recommended_variant"] == "suppression_off"
    assert result["primary_loss"] == "hybrid_consensus_support_loss"


def test_prefers_lowest_vertical_iou_variant_that_reaches_final():
    default = _target_stage(row=True, raw=False)
    raw_only = _target_stage(row=True, raw=True)
    final = _target_stage(row=True, raw=True, size=True, heuristic=True, trimmed=True, final=True)
    variants = _variants(default, suppression_off=raw_only, vertical_iou_0p1=final)
    variants["vertical_iou_0p1"]["vertical_iou"] = 0.1
    result = classify_first_loss(source_trace=_source_trace(), variants=variants)
    assert result["boundary"] == "existing_box_suppression"
    assert result["recommended_variant"] == "vertical_iou_0p1"
    assert result["candidate_reaches_final"] is True


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (_target_stage(row=False), "row_band_construction"),
        (_target_stage(row=True), "raw_probe_generation"),
        (_target_stage(row=True, raw=True), "size_filter"),
        (_target_stage(row=True, raw=True, size=True), "candidate_filter"),
        (
            _target_stage(row=True, raw=True, size=True, heuristic=True),
            "trim",
        ),
        (
            _target_stage(row=True, raw=True, size=True, heuristic=True, trimmed=True),
            "final_set_or_dedup",
        ),
    ],
)
def test_classifies_first_unrecovered_probe_stage(stage, expected):
    result = classify_first_loss(
        source_trace=_source_trace(),
        variants=_variants(stage),
    )
    assert result["boundary"] == expected


def test_classifies_baseline_homr_when_target_absent_before_probe():
    result = classify_first_loss(
        source_trace=_source_trace(baseline=False),
        variants=_variants(_target_stage()),
    )
    assert result == {"boundary": "baseline_homr", "recommended_variant": None}


def test_rejected_paper_experiment_is_not_a_production_filter_option():
    parameters = inspect.signature(filter_probe_candidates).parameters
    assert "fill_paper_region_holes" not in parameters
    assert "paper_overlap_x_padding_ratio" not in parameters
    assert "paper_side_context_width_ratio" not in parameters


def test_tool_local_side_context_can_reproduce_rejected_experiment():
    image = np.zeros((80, 80), dtype=np.uint8)
    image[10:70, 10:70] = 255
    candidate = (39, 25, 43, 55)
    image[candidate[1] : candidate[3], candidate[0] : candidate[2]] = 0
    existing = [(20, 25, 24, 55)]

    kept, dropped = _apply_candidate_filter(
        candidates=[candidate],
        image=image,
        existing_boxes=existing,
        staff_mask=None,
        clef_mask=np.zeros_like(image),
        filter_kwargs={
            "left_margin_ratio": 0.0,
            "min_height_median_ratio": 0.0,
            "min_paper_overlap_ratio": 0.6,
        },
        experimental_side_context_width_ratio=1.0,
    )

    assert kept == [candidate]
    assert dropped == []
