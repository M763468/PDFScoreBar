from __future__ import annotations

from tools.issue255.run_public_homr_on_sr_x4 import (
    _compare_boxes,
    _greedy_match_count,
    _target_support,
)


def test_greedy_match_count_accepts_shifted_vertical_boxes() -> None:
    actual = [(101, 10, 105, 110), (201, 20, 205, 120)]
    reference = [(100, 10, 104, 110), (200, 20, 204, 120)]

    assert _greedy_match_count(actual, reference, 0.5) == 2


def test_compare_boxes_keeps_exact_and_tolerant_results_separate() -> None:
    actual = [(101, 10, 105, 110), (300, 30, 304, 130)]
    reference = [(100, 10, 104, 110), (400, 40, 404, 140)]

    result = _compare_boxes(actual, reference)

    assert result["exact_match"] is False
    assert result["exact_common_count"] == 0
    assert result["tolerant_iou"]["0.5"] == {
        "matched": 1,
        "actual_unmatched": 1,
        "reference_unmatched": 1,
    }


def test_target_support_reports_sr_support_and_hybrid_inclusion() -> None:
    targets = {
        "historical": [{"bbox": [100, 10, 104, 110]}],
        "public": [{"bbox": [300, 30, 304, 130]}],
    }
    sr_boxes = [(101, 10, 105, 110)]
    hybrid_boxes = [(100, 10, 104, 110)]

    result = _target_support(targets, sr_boxes, hybrid_boxes)

    assert result["historical"][0]["sr_supported_iou_gt_0_5"] is True
    assert result["historical"][0]["included_in_recomputed_hybrid"] is True
    assert result["public"][0]["sr_supported_iou_gt_0_5"] is False
    assert result["public"][0]["included_in_recomputed_hybrid"] is False
