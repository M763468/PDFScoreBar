from __future__ import annotations

from tools.issue255.analyze_public_stage_e_consensus_counterfactual import (
    _comparison,
    _consensus,
    _support_summary,
    _variant_classification,
)


def test_consensus_keeps_baseline_boxes_supported_by_either_component() -> None:
    baseline = [
        (0, 0, 4, 100),
        (10, 0, 14, 100),
        (20, 0, 24, 100),
    ]
    sr = [(0, 0, 4, 100)]
    omr = [(10, 0, 14, 100)]

    assert _consensus(baseline, sr, omr) == [
        (0, 0, 4, 100),
        (10, 0, 14, 100),
    ]
    assert _support_summary(baseline, sr, omr) == {
        "both": 0,
        "sr_only": 1,
        "omr_only": 1,
        "neither": 1,
    }


def test_comparison_reports_exact_set_differences() -> None:
    assert _comparison(
        [(0, 0, 4, 100), (10, 0, 14, 100)],
        [(0, 0, 4, 100), (20, 0, 24, 100)],
    ) == {
        "actual_count": 2,
        "reference_count": 2,
        "exact_common_count": 1,
        "actual_only_count": 1,
        "reference_only_count": 1,
        "exact_match": False,
    }


def test_variant_classification_detects_current_consensus_reproduction() -> None:
    historical = [(0, 0, 4, 100)]
    public = [(10, 0, 14, 100)]
    variants = {
        "historical_sr_historical_omr": historical,
        "historical_sr_public_omr": historical,
        "public_sr_historical_omr": public,
        "public_sr_public_omr": public,
    }

    assert (
        _variant_classification(variants, historical, public)
        == "current_consensus_reproduces_both_from_component_inputs"
    )
