from tools.issue245.run_focused_aligned_expansion_cnn import (
    _best_match,
    _score_for_box,
    _target_summary,
)


def test_score_for_box_returns_exact_score() -> None:
    records = [{"bbox": [1, 2, 3, 8], "score": 0.25}]

    assert _score_for_box(records, (1, 2, 3, 8)) == 0.25
    assert _score_for_box(records, (1, 2, 3, 9)) is None


def test_best_match_requires_iou_strictly_above_half() -> None:
    reference = (10, 10, 14, 110)

    result = _best_match(reference, [(10, 60, 14, 160)])

    assert result["iou"] < 0.5
    assert result["accepted"] is False


def test_target_summary_requires_geometry_and_cnn_threshold() -> None:
    target = {"reference": [10, 10, 14, 110]}
    scored = [{"bbox": [10, 10, 14, 110], "score": 0.09}]

    result = _target_summary(target=target, scored=scored, threshold=0.1)

    assert result["iou"] == 1.0
    assert result["accepted"] is False
