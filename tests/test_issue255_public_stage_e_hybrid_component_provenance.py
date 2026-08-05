from __future__ import annotations

from tools.issue255.analyze_public_stage_e_hybrid_component_provenance import (
    _component_comparison,
    _stage_provenance,
    _unique_blockers,
    _unique_cluster_members,
)


def test_component_comparison_reports_exact_set_difference() -> None:
    comparison = _component_comparison(
        [(0, 0, 4, 100), (10, 0, 14, 100)],
        [(0, 0, 4, 100), (20, 0, 24, 100)],
    )

    assert comparison == {
        "historical_count": 2,
        "public_count": 2,
        "exact_common_count": 1,
        "historical_only_count": 1,
        "public_only_count": 1,
        "exact_match": False,
    }


def test_stage_provenance_uses_iou_matching() -> None:
    result = _stage_provenance(
        [10, 20, 14, 120],
        {
            "baseline": [(10, 20, 14, 120)],
            "sr": [(11, 20, 15, 120)],
            "omr": [(100, 20, 104, 120)],
            "hybrid": [(10, 20, 14, 120)],
        },
    )

    assert result["baseline"]["accepted"] is True
    assert result["sr"]["accepted"] is True
    assert result["omr"]["accepted"] is False
    assert result["hybrid"]["accepted"] is True


def test_unique_cluster_members_and_blockers_deduplicate_rows() -> None:
    rows = [
        {
            "public_cluster": {
                "members": [{"bbox": [1, 2, 5, 10]}],
            },
            "historical_existing_suppression_matches": [{"bbox": [20, 30, 24, 130]}],
        },
        {
            "public_cluster": {
                "members": [{"bbox": [1, 2, 5, 10]}],
            },
            "historical_existing_suppression_matches": [{"bbox": [20, 30, 24, 130]}],
        },
    ]

    assert _unique_cluster_members(rows, "public") == [(1, 2, 5, 10)]
    assert _unique_blockers(rows, "historical") == [(20, 30, 24, 130)]
