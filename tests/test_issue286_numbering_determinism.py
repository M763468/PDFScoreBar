from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Staff, System


def _number_with_duplicate_order(*, wider_first: bool) -> System:
    narrow = Barline(bbox=BBox(1788, 2631, 1797, 2729))
    wider = Barline(bbox=BBox(1788, 2993, 1799, 3091))
    right = Barline(bbox=BBox(2200, 2631, 2204, 3091))
    duplicates = [wider, narrow] if wider_first else [narrow, wider]
    system = System(
        staves=[
            Staff(
                bbox=BBox(237, 2577, 2759, 2755),
                barlines=[duplicates[0], right],
            ),
            Staff(
                bbox=BBox(264, 2970, 2761, 3117),
                barlines=[duplicates[1], right],
            ),
        ]
    )
    MeasureNumberer().number_system(system, start_number=1)
    return system


def test_equal_x_duplicate_prefers_wider_barline_independent_of_insertion_order() -> None:
    for wider_first in (False, True):
        system = _number_with_duplicate_order(wider_first=wider_first)

        # The production geometry has a large gap from the system left edge to
        # the first detected barline, so numbering correctly inserts an implicit
        # system-start (ghost) measure before the measured duplicate boundary.
        assert len(system.measures) == 2
        assert system.measures[0].start_bar is not None
        assert system.measures[0].start_bar.is_ghost is True

        measured = system.measures[1]
        assert measured.bbox.x1 == 1799
        assert measured.start_bar is not None
        assert measured.start_bar.bbox == BBox(1788, 2993, 1799, 3091)


def test_distinct_x_near_duplicate_preserves_leftmost_precedence() -> None:
    left = Barline(bbox=BBox(1788, 2631, 1797, 2729))
    wider_right = Barline(bbox=BBox(1789, 2993, 1801, 3091))
    terminal = Barline(bbox=BBox(2200, 2631, 2204, 3091))
    system = System(
        staves=[
            Staff(bbox=BBox(237, 2577, 2759, 2755), barlines=[left, terminal]),
            Staff(bbox=BBox(264, 2970, 2761, 3117), barlines=[wider_right, terminal]),
        ]
    )

    MeasureNumberer().number_system(system, start_number=1)

    # The Issue #286 rule is only an exact-x tie breaker. A wider barline one
    # pixel to the right remains governed by the historical ascending-x rule.
    assert len(system.measures) == 2
    measured = system.measures[1]
    assert measured.start_bar is not None
    assert measured.start_bar.bbox == left.bbox
    assert measured.bbox.x1 == left.bbox.x2
