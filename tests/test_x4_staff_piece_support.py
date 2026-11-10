"""#522: x4 HOMR staff-piece support replacing OMR-DLN hybrid support."""

from __future__ import annotations

from src.common.barline_strokes import StaffRegion
from src.pipeline.steps.hybrid_consensus import (
    apply_x4_iou_consensus_filter,
    apply_x4_staff_piece_consensus_filter,
    x4_staff_piece_support,
)

UNIT = 25.0
# Two staves of one system (Prokofiev Sym5 p005 geometry from #519).
STAVES = [
    StaffRegion((193, 1283, 3464, 1477), UNIT),
    StaffRegion((193, 1619, 3466, 1793), UNIT),
]
LONG = (2687, 1345, 2688, 1771)
UPPER_X4 = (2683, 1347, 2690, 1454)
LOWER_X4 = (2681, 1660, 2688, 1765)


def test_long_box_is_supported_when_every_staff_piece_has_an_x4_stroke():
    assert x4_staff_piece_support(LONG, [UPPER_X4, LOWER_X4], STAVES)
    assert apply_x4_staff_piece_consensus_filter(
        baseline_boxes=[LONG], sr_boxes=[UPPER_X4, LOWER_X4], staves=STAVES
    ) == [list(LONG)]


def test_x4_stroke_on_only_one_staff_is_never_propagated():
    assert not x4_staff_piece_support(LONG, [UPPER_X4], STAVES)
    assert not x4_staff_piece_support(LONG, [LOWER_X4], STAVES)
    assert (
        apply_x4_staff_piece_consensus_filter(
            baseline_boxes=[LONG], sr_boxes=[UPPER_X4], staves=STAVES
        )
        == []
    )


def test_single_staff_box_needs_ordinary_iou_support():
    single = (2687, 1345, 2688, 1477)
    assert not x4_staff_piece_support(single, [UPPER_X4], STAVES)
    # The ordinary IoU path still applies.
    assert apply_x4_staff_piece_consensus_filter(
        baseline_boxes=[UPPER_X4], sr_boxes=[UPPER_X4], staves=STAVES
    ) == [list(UPPER_X4)]


def _lower_at(offset: int) -> tuple[int, int, int, int]:
    """x4 lower-staff stroke whose center is ``offset`` px right of the long box center."""
    return (2684 + offset, 1660, 2691 + offset, 1765)  # center 2687.5 + offset


def test_center_tolerance_is_half_a_staff_unit():
    assert x4_staff_piece_support(LONG, [UPPER_X4, _lower_at(12)], STAVES)  # 12 <= 12.5
    assert not x4_staff_piece_support(LONG, [UPPER_X4, _lower_at(13)], STAVES)


def test_short_x4_fragments_such_as_stems_do_not_count():
    stem = (2685, 1700, 2687, 1740)  # 40px < 2 * unit
    assert not x4_staff_piece_support(LONG, [UPPER_X4, stem], STAVES)


def test_thresholds_scale_with_unit_size():
    small = [StaffRegion(st.bbox, 10.0) for st in STAVES]
    assert x4_staff_piece_support(LONG, [UPPER_X4, _lower_at(5)], small)  # 5 <= 0.5 * 10
    assert not x4_staff_piece_support(LONG, [UPPER_X4, _lower_at(6)], small)


def test_x4_iou_seed_filter_ignores_any_other_support_source():
    assert apply_x4_iou_consensus_filter(baseline_boxes=[UPPER_X4], sr_boxes=[UPPER_X4]) == [
        list(UPPER_X4)
    ]
    assert apply_x4_iou_consensus_filter(baseline_boxes=[UPPER_X4], sr_boxes=[]) == []


# --- #522 review: boundary cases --------------------------------------------------


def test_stroke_must_lie_mostly_inside_the_piece():
    # Lower piece is y 1619..1771 (152px). A 100px stroke with 79px inside fails, 80px passes.
    outside_79 = (2684, 1619 - 21, 2691, 1619 + 79)
    outside_80 = (2684, 1619 - 20, 2691, 1619 + 80)
    assert not x4_staff_piece_support(LONG, [UPPER_X4, outside_79], STAVES)
    assert x4_staff_piece_support(LONG, [UPPER_X4, outside_80], STAVES)


def test_three_staff_system_requires_every_piece():
    staves = [
        StaffRegion((193, 1283, 3464, 1477), UNIT),
        StaffRegion((193, 1619, 3466, 1793), UNIT),
        StaffRegion((193, 1950, 3466, 2124), UNIT),
    ]
    long3 = (2687, 1345, 2688, 2100)
    third = (2684, 1990, 2691, 2095)
    assert x4_staff_piece_support(long3, [UPPER_X4, LOWER_X4, third], staves)
    # A missing middle-staff stroke is never bridged by the outer staves.
    assert not x4_staff_piece_support(long3, [UPPER_X4, third], staves)


def test_staff_without_a_region_is_not_split_into_a_piece():
    # staff_regions_from_mask drops staves whose unit_size could not be estimated; the
    # box then intersects one region only and gets no staff-piece support.
    only_upper = [STAVES[0]]
    assert not x4_staff_piece_support(LONG, [UPPER_X4, LOWER_X4], only_upper)


def test_nearby_double_barline_stroke_supports_only_within_half_a_unit():
    # The thick line of a double/final barline about 0.4 unit away still supports the
    # same boundary; a stroke 0.6 unit away (another boundary) does not.
    thick_near = _lower_at(10)
    other = _lower_at(15)
    assert x4_staff_piece_support(LONG, [UPPER_X4, thick_near], STAVES)
    assert not x4_staff_piece_support(LONG, [UPPER_X4, other], STAVES)


def test_box_spanning_less_than_two_units_into_a_staff_is_not_split():
    # normalize_staff_stroke requires >= 2 units of overlap per staff, so a connector
    # tail that only grazes the next staff is not treated as a multi-staff barline.
    grazing = (2687, 1345, 2688, 1619 + 40)  # 40px < 2 * 25 into the lower staff
    assert not x4_staff_piece_support(grazing, [UPPER_X4, LOWER_X4], STAVES)
