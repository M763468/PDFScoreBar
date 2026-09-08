from __future__ import annotations

from tools.issue294.diagnose_mapping_guarded_mmr_geometry_deltas import (
    _snapshot_delta,
    bbox_delta,
    differing_override_keys,
)


def test_differing_override_keys_detects_presence_and_value_changes() -> None:
    frozen = [
        {"page": 0, "system": 1, "measure": 2, "skip": 3},
        {"page": 0, "system": 2, "measure": 0, "skip": 5},
    ]
    native = [
        {"page": 0, "system": 1, "measure": 2, "skip": 9},
        {"page": 0, "system": 3, "measure": 0, "skip": 5},
    ]

    assert differing_override_keys(frozen, native) == [
        (0, 1, 2),
        (0, 2, 0),
        (0, 3, 0),
    ]


def test_bbox_delta_classifies_horizontal_and_vertical_motion() -> None:
    delta = bbox_delta([10, 20, 50, 60], [12, 18, 54, 62])

    assert delta["equal"] is False
    assert delta["native_minus_frozen_edges"] == [2.0, -2.0, 4.0, 2.0]
    assert delta["native_minus_frozen_size"] == [2.0, 4.0]
    assert delta["center_delta"] == [3.0, 0.0]
    assert delta["horizontal_changed"] is True
    assert delta["vertical_changed"] is True
    assert 0.0 < delta["iou"] < 1.0


def test_snapshot_delta_separates_primary_horizontal_from_vertical_change() -> None:
    frozen = {
        "present": True,
        "base_measure_bbox": [10, 20, 50, 60],
        "views": {
            "primary": {"measure_bbox": [10, 18, 50, 62]},
            "implicit_start_alternate": {"measure_bbox": [10, 18, 50, 62]},
            "fallback": {"measure_bbox": [10, 20, 50, 60]},
        },
    }
    native = {
        "present": True,
        "base_measure_bbox": [12, 20, 50, 60],
        "views": {
            "primary": {"measure_bbox": [12, 18, 50, 62]},
            "implicit_start_alternate": {"measure_bbox": [12, 18, 50, 62]},
            "fallback": {"measure_bbox": [12, 20, 50, 60]},
        },
    }

    delta = _snapshot_delta(frozen, native)

    assert delta["comparable"] is True
    assert delta["any_measure_geometry_changed"] is True
    assert delta["primary_horizontal_changed"] is True
    assert delta["primary_vertical_changed"] is False


def test_snapshot_delta_reports_missing_measure_without_guessing() -> None:
    delta = _snapshot_delta(
        {"present": False, "reason": "measure_absent"},
        {"present": True},
    )

    assert delta == {
        "comparable": False,
        "frozen_present": False,
        "native_present": True,
    }
