"""Exercise image geometry without loading HOMR models or polluting imports."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import cv2
import numpy as np
import pytest


@pytest.fixture
def candidates(monkeypatch):
    # Stub only the external mask/box boundary; OpenCV processing stays real.
    barlines = ModuleType("homr.bar_line_detection")
    boxes = ModuleType("homr.bounding_boxes")
    barlines.prepare_bar_line_image = lambda mask: mask

    def capture_boxes(mask, **kwargs):
        return [(mask.copy(), kwargs)]

    boxes.create_rotated_bounding_boxes = capture_boxes
    monkeypatch.setitem(sys.modules, "homr", ModuleType("homr"))
    monkeypatch.setitem(sys.modules, barlines.__name__, barlines)
    monkeypatch.setitem(sys.modules, boxes.__name__, boxes)
    path = Path(__file__).resolve().parents[1] / "src/homr_runtime/barline_candidates.py"
    spec = importlib.util.spec_from_file_location("_test_homr_candidates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vertical_runs_keep_strong_lines_and_mask_out_other_staffs(candidates):
    image = np.full((64, 32, 3), 255, dtype=np.uint8)
    image[8:48, 5] = 0
    image[8:48, 20] = 0
    image[8:16, 10] = 0
    staff_mask = np.zeros((32, 16), dtype=np.uint8)
    staff_mask[:, :8] = 255
    [(mask, options)] = candidates.generate_vertical_run_candidates(image, staff_mask)
    assert np.count_nonzero(mask[:, 5]) == 40
    assert not np.any(mask[:, 10:])
    assert options == {"skip_merging": True, "min_size": (1, 20)}


def test_weak_runs_recover_short_gray_lines(candidates):
    image = np.full((40, 20, 3), 255, dtype=np.uint8)
    image[5:20, 8] = 100
    [(strong, _)] = candidates.generate_vertical_run_candidates(image, None)
    [(weak, options)] = candidates.generate_vertical_run_candidates_weak(image, None)
    assert not np.any(strong)
    assert np.count_nonzero(weak[:, 8]) == 15
    assert options == {"skip_merging": True, "min_size": (1, 10)}


@pytest.mark.parametrize("variant,minimum", [("relaxed", 3), ("dilated", 3), ("tiny", 1)])
def test_connected_component_variants_preserve_box_contract(candidates, variant, minimum):
    original = np.zeros((32, 20), dtype=np.uint8)
    original[10:12, 8] = 255
    [(mask, options)] = getattr(candidates, f"generate_barline_cc_{variant}")(original)
    assert options == {"skip_merging": True, "min_size": (1, minimum)}
    if variant == "dilated":
        assert np.count_nonzero(mask) == 6
        assert np.all(mask[8:14, 8] == 255)
    else:
        np.testing.assert_array_equal(mask, original)


@pytest.mark.parametrize("weak,minimum", [(False, 15), (True, 10)])
def test_sobel_edges_respect_staff_mask(candidates, weak, minimum):
    image = np.full((64, 32, 3), 255, dtype=np.uint8)
    image[8:48, 5] = 0
    image[8:48, 20] = 0
    staff_mask = np.zeros((64, 32), dtype=np.uint8)
    staff_mask[:, :16] = 255
    function = candidates.generate_sobel_vertical_candidates
    if weak:
        function = candidates.generate_sobel_vertical_candidates_weak
    [(mask, options)] = function(image, staff_mask)
    assert np.any(mask[:, 4:7])
    assert not np.any(mask[:, 16:])
    assert options == {"skip_merging": True, "min_size": (1, minimum)}


def test_column_sum_preserves_disconnected_runs_and_empty_result(candidates):
    image = np.full((64, 32, 3), 255, dtype=np.uint8)
    image[4:14, 5] = 100
    image[30:40, 5] = 100
    image[4:23, 10] = 0
    [(mask, options)] = candidates.generate_column_sum_candidates(image, None)
    assert np.count_nonzero(mask[:, 5]) == 20
    assert not np.any(mask[:, 10])
    assert options == {"skip_merging": True, "min_size": (1, 20)}
    assert candidates.generate_column_sum_candidates(image, np.zeros((64, 32), np.uint8)) == []


def test_hough_rejects_short_and_slanted_lines(candidates, monkeypatch):
    image = np.full((64, 32, 3), 255, dtype=np.uint8)
    lines = np.array([[[5, 5, 5, 45]], [[10, 5, 10, 15]], [[15, 5, 30, 45]]])
    captured = {}

    def hough(edges, **kwargs):
        captured.update(kwargs)
        assert edges.shape == (64, 32)
        return lines

    monkeypatch.setattr(cv2, "HoughLinesP", hough)
    [(mask, options)] = candidates.generate_hough_vertical_candidates(image, None)
    assert np.count_nonzero(mask[:, 5]) == 41
    assert not np.any(mask[:, 10:])
    assert options == {"skip_merging": True, "min_size": (1, 25)}
    assert captured == {
        "rho": 1,
        "theta": np.pi / 180.0,
        "threshold": 50,
        "minLineLength": 25,
        "maxLineGap": 6,
    }
    monkeypatch.setattr(cv2, "HoughLinesP", lambda *args, **kwargs: None)
    assert candidates.generate_hough_vertical_candidates(image, None) == []
