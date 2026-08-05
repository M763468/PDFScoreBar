from __future__ import annotations

from tools.issue255.analyze_public_stage_e_row_band_suppression import (
    _classification,
    _cluster_records,
    _suppression_matches,
)


def test_row_band_geometry_changes_existing_suppression() -> None:
    existing = [(1515, 649, 1523, 753)]

    public = _suppression_matches(existing, [617, 696], 1520.0)
    historical = _suppression_matches(existing, [621, 704], 1520.0)

    assert public == []
    assert historical == [
        {
            "bbox": [1515, 649, 1523, 753],
            "x_center": 1519.0,
            "y_center": 701.0,
            "x_center_distance": 1.0,
        }
    ]
    assert (
        _classification(public, historical)
        == "row_band_geometry_changes_existing_suppression"
    )


def test_cluster_records_retains_members_and_median_band() -> None:
    records = _cluster_records(
        [
            (100, 617, 104, 696),
            (200, 619, 204, 698),
            (300, 650, 304, 753),
        ]
    )

    assert len(records) == 2
    assert records[0]["band"] == [618, 697]
    assert records[0]["member_count"] == 2
    assert records[1]["band"] == [650, 753]
