from __future__ import annotations

from tools.issue245.run_fresh_row_band_rescue_probe import (
    _best_match,
    _classify_target,
    _semantic_delta,
)


def test_best_match_accepts_supported_barline() -> None:
    reference = (100, 200, 104, 300)
    candidates = [(100, 200, 104, 300), (500, 200, 504, 300)]

    result = _best_match(reference, candidates)

    assert result["accepted"] is True
    assert result["max_iou"] == 1.0
    assert result["best_bbox"] == [100, 200, 104, 300]


def test_best_match_rejects_short_geometry() -> None:
    reference = (100, 200, 104, 300)
    candidates = [(100, 260, 104, 300)]

    result = _best_match(reference, candidates)

    assert result["accepted"] is False
    assert result["max_iou"] <= 0.5


def test_semantic_delta_reports_added_and_removed_boxes() -> None:
    control = [(1, 2, 3, 4), (5, 6, 7, 8)]
    variant = [(5, 6, 7, 8), (9, 10, 11, 12)]

    result = _semantic_delta(control, variant)

    assert result["added_count"] == 1
    assert result["removed_count"] == 1
    assert result["added_examples"] == [[9, 10, 11, 12]]
    assert result["removed_examples"] == [[1, 2, 3, 4]]


def _matches(*, accepted: str | None = None) -> dict[str, dict[str, object]]:
    names = (
        "row_stats_control",
        "row_stats_pad_025",
        "row_stats_pad_050",
        "row_stats_pad_075",
        "staff_mask",
    )
    return {
        name: {"accepted": name == accepted, "max_iou": 1.0 if name == accepted else 0.0}
        for name in names
    }


def test_classify_target_prefers_smallest_restoring_padding() -> None:
    matches = _matches(accepted="row_stats_pad_050")
    matches["row_stats_pad_075"]["accepted"] = True
    matches["staff_mask"]["accepted"] = True

    assert _classify_target(matches) == "restored_by_row_stats_pad_050"


def test_classify_target_reports_staff_mask_rescue() -> None:
    assert _classify_target(_matches(accepted="staff_mask")) == "restored_by_staff_mask"


def test_classify_target_reports_unresolved() -> None:
    assert _classify_target(_matches()) == "unresolved"
