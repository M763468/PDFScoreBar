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
