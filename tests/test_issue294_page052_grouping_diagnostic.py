from __future__ import annotations

from tools.issue294.diagnose_page052_grouping import _pair_decision


def test_explicit_connector_absence_is_a_hard_split_signal() -> None:
    result = _pair_decision(
        gap=100,
        avg_height=100,
        aligned_count=4,
        explicit_evidence=True,
        left_connector_present=False,
    )

    assert result["decision"] == "split"
    assert result["reason"] == "explicit_connector_absence"
    assert result["within_distance"] is True


def test_same_geometry_merges_when_negative_evidence_is_unknown() -> None:
    result = _pair_decision(
        gap=100,
        avg_height=100,
        aligned_count=4,
        explicit_evidence=False,
        left_connector_present=False,
    )

    assert result["decision"] == "merge"
    assert result["reason"] == "distance_and_alignment"
