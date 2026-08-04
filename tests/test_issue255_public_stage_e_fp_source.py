from __future__ import annotations

from tools.issue255.analyze_public_stage_e_fp_source import (
    _bands,
    _classification,
)


def test_classification_detects_row_band_threshold_crossing() -> None:
    assert (
        _classification(
            historical_raw_exact=False,
            public_hybrid_exact=False,
            historical_hybrid_exact=False,
            public_band=[617, 696],
            historical_band=[649, 753],
            public_ratio=0.61,
            historical_ratio=0.58,
        )
        == "row_band_geometry_crosses_probe_threshold"
    )


def test_classification_prefers_public_hybrid_existing_box() -> None:
    assert (
        _classification(
            historical_raw_exact=False,
            public_hybrid_exact=True,
            historical_hybrid_exact=False,
            public_band=[617, 696],
            historical_band=[649, 753],
            public_ratio=0.9,
            historical_ratio=0.4,
        )
        == "introduced_as_public_hybrid_existing_box"
    )


def test_bands_reproduces_historical_row_stats_contract() -> None:
    boxes = [
        (0, 617, 4, 696),
        (10, 619, 14, 698),
        (20, 650, 24, 753),
        (30, 652, 34, 755),
    ]

    assert _bands(boxes) == [(617, 696), (650, 753)]
