from __future__ import annotations

import pytest

from tools.issue264.phase_c_fixture_rebase import (
    map_measure_bbox,
    measure_for_index,
    rebase_expected_overrides,
)


def _numbering(rows: list[tuple[float, list[tuple[float, float]]]]) -> dict:
    systems = []
    for y, x_ranges in rows:
        systems.append(
            {
                "staves": [],
                "measures": [
                    {"number": index + 1, "bbox": [x1, y, x2, y + 80]}
                    for index, (x1, x2) in enumerate(x_ranges)
                ],
            }
        )
    return {"pages": [{"page_number": 0, "width": 1000, "height": 1400, "systems": systems}]}


def test_fixture_rebase_tracks_same_page_region_after_system_index_shift() -> None:
    historical = _numbering(
        [
            (100, [(0, 200), (200, 400)]),
            (300, [(0, 200), (200, 400)]),
            (500, [(0, 200), (200, 400)]),
        ]
    )
    current = _numbering(
        [
            (100, [(0, 200), (200, 400)]),
            (500, [(0, 200), (200, 400)]),
        ]
    )
    expected = {"overrides": [{"page": 0, "system": 2, "measure": 1, "skip": 4}]}

    rebased, mappings = rebase_expected_overrides(
        expected,
        historical,
        current,
        global_page_index=27,
    )

    assert rebased["overrides"] == [
        {"page": 27, "system": 1, "measure": 1, "skip": 4}
    ]
    assert mappings[0]["historical_key"] == [27, 2, 1]
    assert mappings[0]["current_key"] == [27, 1, 1]
    assert mappings[0]["changed"] is True
    assert mappings[0]["method"] == "historical_center_in_current_bbox"


def test_fixture_rebase_preserves_index_when_geometry_is_unchanged() -> None:
    numbering = _numbering([(100, [(0, 200), (200, 400)])])
    expected = {"measure_overrides": [{"page": 99, "system": 0, "measure": 0, "skip": 2}]}

    rebased, mappings = rebase_expected_overrides(
        expected,
        numbering,
        numbering,
        global_page_index=5,
    )

    assert rebased["overrides"][0]["page"] == 5
    assert rebased["overrides"][0]["system"] == 0
    assert rebased["overrides"][0]["measure"] == 0
    assert mappings[0]["changed"] is False


def test_fixture_rebase_can_use_overlap_when_center_moved_just_outside() -> None:
    historical = _numbering([(100, [(100, 300)])])
    current = _numbering([(100, [(190, 390)])])
    ref = measure_for_index(historical, system=0, measure=0)

    mapped, detail = map_measure_bbox(ref, current, minimum_overlap=0.50)

    assert (mapped.system, mapped.measure) == (0, 0)
    assert detail["method"] == "historical_center_in_current_bbox"
    assert detail["overlap_score"] >= 0.50


def test_fixture_rebase_rejects_weak_spatial_match() -> None:
    historical = _numbering([(100, [(0, 100)])])
    current = _numbering([(900, [(700, 800)])])
    ref = measure_for_index(historical, system=0, measure=0)

    with pytest.raises(ValueError, match="Could not spatially rebase"):
        map_measure_bbox(ref, current)


def test_fixture_rebase_rejects_multiple_gt_items_mapping_to_same_current_measure() -> None:
    historical = _numbering([(100, [(0, 100), (100, 200)])])
    current = _numbering([(100, [(0, 200)])])
    expected = {
        "overrides": [
            {"page": 0, "system": 0, "measure": 0, "skip": 2},
            {"page": 0, "system": 0, "measure": 1, "skip": 3},
        ]
    }

    with pytest.raises(ValueError, match="Multiple historical fixtures"):
        rebase_expected_overrides(expected, historical, current, global_page_index=0)
