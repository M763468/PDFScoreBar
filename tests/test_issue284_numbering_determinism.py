from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import BBox, Barline, Staff, System


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
        assert len(system.measures) == 1
        assert system.measures[0].bbox.x1 == 1799
        assert system.measures[0].start_bar is not None
        assert system.measures[0].start_bar.bbox == BBox(1788, 2993, 1799, 3091)
