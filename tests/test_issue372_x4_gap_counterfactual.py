"""Focused tests for the Issue #372 retained x4-gap counterfactual policy."""

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    build_x4_gap_fallback,
)


def test_promotes_only_x4_boxes_without_baseline_iou_support() -> None:
    baseline = [
        [100, 100, 110, 200],
        [300, 100, 310, 200],
    ]
    x4 = [
        [101, 100, 111, 200],  # overlaps baseline[0], should not promote
        [200, 100, 210, 200],  # no baseline overlap, should promote
        [301, 100, 311, 200],  # overlaps baseline[1], should not promote
    ]
    current_hybrid = [[100, 100, 110, 200]]

    fallback, promoted = build_x4_gap_fallback(
        baseline_boxes=baseline,
        x4_boxes=x4,
        current_hybrid_boxes=current_hybrid,
    )

    assert promoted == [[200, 100, 210, 200]]
    assert fallback == [
        [100, 100, 110, 200],
        [200, 100, 210, 200],
    ]


def test_deduplicates_promoted_x4_boxes() -> None:
    fallback, promoted = build_x4_gap_fallback(
        baseline_boxes=[],
        x4_boxes=[
            [200, 100, 210, 200],
            [200, 100, 210, 200],
        ],
        current_hybrid_boxes=[],
    )

    assert promoted == [[200, 100, 210, 200]]
    assert fallback == [[200, 100, 210, 200]]
