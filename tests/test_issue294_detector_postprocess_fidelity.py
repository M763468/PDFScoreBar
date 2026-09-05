from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.issue294.run_latest_homr_detector_original import BarlinePrediction, _postprocess


def _prediction(box: tuple[int, int, int, int]) -> BarlinePrediction:
    return BarlinePrediction(
        pred_bbox=box,
        orig_bbox=box,
        system_index=-1,
        staff_index=-1,
    )


def test_thin_barline_equal_height_overlap_keeps_existing(monkeypatch) -> None:
    """Match HomrPredictor: overlap branch replaces only when the extra is taller."""

    import src.common.thin_barline_finder as thin_barline_finder

    existing = (10, 10, 12, 30)
    equal_height_overlap = (11, 10, 13, 30)
    monkeypatch.setattr(
        thin_barline_finder,
        "detect_thin_vertical_runs",
        lambda *_args, **_kwargs: [equal_height_overlap],
    )

    result = _postprocess(
        Path("page.png"),
        np.full((64, 64, 3), 255, dtype=np.uint8),
        [_prediction(existing)],
        np.zeros((64, 64), dtype=np.uint8),
    )

    assert [item.orig_bbox for item in result] == [existing]


def test_thin_barline_equal_height_center_gap_replaces_existing(monkeypatch) -> None:
    """Match HomrPredictor: center-gap branch permits equal-height replacement."""

    import src.common.thin_barline_finder as thin_barline_finder

    existing = (10, 10, 12, 30)
    equal_height_center_gap = (11, 25, 13, 45)
    monkeypatch.setattr(
        thin_barline_finder,
        "detect_thin_vertical_runs",
        lambda *_args, **_kwargs: [equal_height_center_gap],
    )

    result = _postprocess(
        Path("page.png"),
        np.full((64, 64, 3), 255, dtype=np.uint8),
        [_prediction(existing)],
        np.zeros((64, 64), dtype=np.uint8),
    )

    assert [item.orig_bbox for item in result] == [equal_height_center_gap]
