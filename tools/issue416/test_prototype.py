"""Semantic controls for experimental rules, without dataset/model dependencies."""

import numpy as np
import pytest

from tools.issue416.prototype import (
    StaffRegion,
    deduplicate_accepted,
    normalize_box,
    split_double_stroke,
)


@pytest.mark.parametrize("scale", [1, 2, 4])
def test_connector_tail_is_clipped_but_ordinary_stroke_is_stable(scale):
    def box(coords):
        return tuple(v * scale for v in coords)

    staff = StaffRegion(box((0, 100, 200, 200)), 25 * scale)
    assert normalize_box(box((50, 25, 54, 200)), [staff], allow_single_tail=True) == [
        box((50, 100, 54, 200))
    ]
    assert normalize_box(box((50, 105, 54, 195)), [staff]) == [box((50, 105, 54, 195))]


def test_multistaff_pieces_keep_separate_staff_positions():
    staves = [StaffRegion((0, 0, 200, 100), 25), StaffRegion((0, 200, 200, 300), 25)]
    assert normalize_box((50, 0, 54, 300), staves) == [(50, 0, 54, 100), (50, 200, 54, 300)]


def test_dedup_preserves_separate_strokes_and_same_x_other_staff():
    rows = [
        dict(bbox=b, score=s)
        for b, s in [
            ((50, 0, 54, 100), 0.99),
            ((51, 1, 55, 101), 0.9),
            ((58, 0, 62, 100), 0.98),
            ((50, 200, 54, 300), 0.97),
        ]
    ]
    kept, removed = deduplicate_accepted(rows, unit_size=25)
    assert {tuple(r["bbox"]) for r in kept} == {
        (50, 0, 54, 100),
        (58, 0, 62, 100),
        (50, 200, 54, 300),
    }
    assert len(removed) == 1


@pytest.mark.parametrize("scale", [1, 2, 4])
def test_double_stroke_split_does_not_split_a_single_wide_stroke(scale):
    image = np.full((200 * scale, 200 * scale), 255, dtype=np.uint8)
    image[30 * scale : 130 * scale, 50 * scale : 54 * scale] = 0
    image[30 * scale : 130 * scale, 62 * scale : 66 * scale] = 0
    box = tuple(v * scale for v in (50, 30, 66, 130))
    pieces = split_double_stroke(image, box, unit_size=25 * scale)
    assert pieces == [tuple(v * scale for v in b) for b in [(50, 30, 54, 130), (62, 30, 66, 130)]]
    image[30 * scale : 130 * scale, 50 * scale : 66 * scale] = 0
    assert split_double_stroke(image, box, unit_size=25 * scale) == [box]


def test_uncertain_unit_fails_explicitly():
    with pytest.raises(ValueError):
        StaffRegion((0, 0, 200, 100), float("nan"))


def test_geometry_representative_retains_its_own_actual_score():
    rows = [
        dict(bbox=(50, 0, 54, 100), score=0.51),
        dict(bbox=(51, 0, 55, 100), score=0.99),
    ]
    kept, removed = deduplicate_accepted(rows, unit_size=25, preserve_geometry=True)
    assert len(removed) == 1
    assert kept == [dict(bbox=(50, 0, 54, 100), score=0.51)]


def test_rejected_single_tail_ablation_is_disabled_by_default():
    staff = StaffRegion((0, 100, 200, 200), 25)
    source = (50, 25, 54, 200)
    assert normalize_box(source, [staff]) == [source]
