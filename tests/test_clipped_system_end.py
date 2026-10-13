"""Clipped original scans may have an open last measure; blank tails may not."""

import cv2
import numpy as np
import pytest

from src.measure_numbering.clipped_end import ClippedSystemEndDetector
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Staff, System


def scan(*, scale=1, staff_count=1, margin=0, line_count=5, symbol=True):
    unit = 10 * scale
    width = 400 * scale
    height = (staff_count * 80 + 20) * scale
    image = np.full((height, width), 255, np.uint8)
    staves = []
    for i in range(staff_count):
        y = (20 + i * 80) * scale
        staff = Staff(BBox(0, y - 5 * scale, width, y + 45 * scale), unit_size=unit)
        for line in range(line_count):
            image[y + line * unit : y + line * unit + scale, : width - margin * scale] = 0
        for x in (0, 100, 200, 300):
            x *= scale
            image[y : y + 4 * unit + scale, x : x + scale] = 0
            staff.barlines.append(Barline(BBox(x, y, x + scale, y + 4 * unit + scale)))
        if symbol:
            cv2.ellipse(
                image,
                (350 * scale, y + 2 * unit + 3 * scale),
                (5 * scale, 3 * scale),
                0,
                0,
                360,
                0,
                -1,
            )
            image[y + 3 * scale : y + 2 * unit + 3 * scale, 355 * scale : 357 * scale] = 0
        staves.append(staff)
    return image, System(staves=staves)


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("staff_count", [1, 3, 4])
def test_clipped_scan_counts_shared_last_interval_once_and_preserves_mmr(scale, staff_count):
    image, system = scan(scale=scale, staff_count=staff_count)
    detector = ClippedSystemEndDetector()
    detector.apply([system], image)
    # Both Phase A and a repeat application see only one shared logical boundary.
    detector.apply([system], image)
    numberer = MeasureNumberer()
    assert numberer.number_system(system, 1) == 5
    assert [m.number for m in system.measures] == [1, 2, 3, 4]
    assert system.measures[-1].bbox.x2 == image.shape[1]
    assert system.measures[-1].end_bar.is_ghost
    assert numberer.number_system(system, 1, overrides={3: {"skip": 4}}) == 9
    assert [m.number for m in system.measures] == [1, 2, 3, 4]
    assert system.measures[-1].attribute.skip == 4


@pytest.mark.parametrize(
    "case",
    [
        "blank_tail",
        "margin",
        "four_lines",
        "unknown_spacing",
        "outside_ink",
        "short_tail",
        "detected_end",
    ],
)
def test_clipping_needs_source_lines_and_music_not_mask_extension(case):
    image, system = scan(
        margin=20 if case == "margin" else 0,
        line_count=4 if case == "four_lines" else 5,
        symbol=case not in ("blank_tail", "outside_ink"),
    )
    staff = system.staves[0]
    if case == "unknown_spacing":
        staff.unit_size = None
    elif case == "outside_ink":
        image[65:70, 340:370] = 0  # Caption/hairpin below the original five lines.
    elif case == "short_tail":
        staff.barlines.append(Barline(BBox(370, 20, 372, 61)))
    elif case == "detected_end":
        staff.barlines.append(Barline(BBox(398, 20, 400, 61)))
    count = len(staff.barlines)
    ClippedSystemEndDetector().apply([system], image)
    assert len(staff.barlines) == count
    assert not any(bar.is_ghost for bar in staff.barlines)


def test_missing_image_does_not_infer_end_from_staff_bbox():
    _, system = scan()
    assert MeasureNumberer().number_system(system, 1) == 4
    assert len(system.measures) == 3
