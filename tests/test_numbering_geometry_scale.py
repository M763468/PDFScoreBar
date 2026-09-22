from __future__ import annotations

import numpy as np

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.types import Barline, BBox, Staff


def _staff(
    *,
    scale: int,
    y1: int,
    y2: int,
    bar_xs: list[int],
) -> Staff:
    unit = 25 * scale
    return Staff(
        bbox=BBox(0, y1 * scale, 500 * scale, y2 * scale),
        barlines=[
            Barline(
                bbox=BBox(
                    x * scale,
                    y1 * scale,
                    x * scale + 2 * scale,
                    y2 * scale,
                )
            )
            for x in bar_xs
        ],
        unit_size=float(unit),
    )


def test_builder_alignment_tolerance_is_resolution_independent() -> None:
    builder = SystemBuilder()

    for scale in (1, 2):
        upper = _staff(scale=scale, y1=100, y2=200, bar_xs=[100])
        within = _staff(scale=scale, y1=230, y2=330, bar_xs=[108])
        outside = _staff(scale=scale, y1=230, y2=330, bar_xs=[113])

        assert len(builder._find_aligned_pairs(upper, within)) == 1
        assert builder._find_aligned_pairs(upper, outside) == []


def test_builder_small_gap_connection_shortcut_scales_with_unit_size() -> None:
    builder = SystemBuilder()

    for scale in (1, 2):
        upper = _staff(scale=scale, y1=100, y2=200, bar_xs=[100])
        lower = _staff(scale=scale, y1=204, y2=304, bar_xs=[100])
        aligned = builder._find_aligned_pairs(upper, lower)
        image = np.full((400 * scale, 600 * scale), 255, dtype=np.uint8)

        assert builder._check_aligned_connection(upper, lower, aligned, image)


def test_builder_barline_staff_overlap_floor_scales_with_unit_size() -> None:
    builder = SystemBuilder()

    for scale in (1, 2):
        staff = _staff(scale=scale, y1=100, y2=200, bar_xs=[])
        accepted = Barline(
            bbox=BBox(
                100 * scale,
                189 * scale,
                102 * scale,
                211 * scale,
            )
        )
        rejected = Barline(
            bbox=BBox(
                200 * scale,
                191 * scale,
                202 * scale,
                209 * scale,
            )
        )

        builder._assign_barlines_to_staves([staff], [accepted, rejected])

        assert accepted in staff.barlines
        assert rejected not in staff.barlines
