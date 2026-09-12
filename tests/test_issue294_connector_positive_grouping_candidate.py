from __future__ import annotations

from src.measure_numbering.types import Barline, BBox, Staff
from tools.issue294.evaluate_connector_positive_grouping_candidate import (
    ConnectorPositiveWithinDistanceBuilder,
)


def _staff_pair(*, gap: int, height: int = 100) -> tuple[Staff, Staff]:
    first = Staff(bbox=BBox(0, 0, 400, height))
    second_y1 = height + gap
    second = Staff(bbox=BBox(0, second_y1, 400, second_y1 + height))
    return first, second


def _aligned_barlines(first: Staff, second: Staff, xs: list[int]) -> list[Barline]:
    bars: list[Barline] = []
    for x in xs:
        bars.append(Barline(bbox=BBox(x, first.bbox.y1, x + 2, first.bbox.y2)))
        bars.append(Barline(bbox=BBox(x, second.bbox.y1, x + 2, second.bbox.y2)))
    return bars


def _evidence(present: bool):
    return {"staff_pairs": [{"staff_pair": [0, 1], "left_connector_present": present}]}


def test_positive_connector_merges_within_normal_distance_without_alignment() -> None:
    builder = ConnectorPositiveWithinDistanceBuilder()
    first, second = _staff_pair(gap=90)

    systems = builder.build_systems(
        [first, second],
        [],
        connector_evidence=_evidence(True),
    )

    assert len(systems) == 1
    assert len(systems[0].staves) == 2


def test_explicit_connector_absence_remains_hard_split() -> None:
    builder = ConnectorPositiveWithinDistanceBuilder()
    first, second = _staff_pair(gap=90)
    bars = _aligned_barlines(first, second, [100, 200, 300])

    systems = builder.build_systems(
        [first, second],
        bars,
        connector_evidence=_evidence(False),
    )

    assert len(systems) == 2


def test_unknown_connector_with_no_alignment_remains_split() -> None:
    builder = ConnectorPositiveWithinDistanceBuilder()
    first, second = _staff_pair(gap=90)

    systems = builder.build_systems([first, second], [])

    assert len(systems) == 2


def test_near_threshold_positive_connector_still_requires_alignment() -> None:
    builder = ConnectorPositiveWithinDistanceBuilder()
    first, second = _staff_pair(gap=153)

    systems = builder.build_systems(
        [first, second],
        [],
        connector_evidence=_evidence(True),
    )

    assert len(systems) == 2
