from __future__ import annotations

from pathlib import Path

from tools.issue245.run_focused_homr_probe import (
    detection_path,
    normalize_box,
    tolerant_match_count,
    vertical_overlap_ratio,
)


def test_normalize_box_rounds_numeric_coordinates() -> None:
    assert normalize_box([1.2, 2.6, 3.4, 4.8]) == (1, 3, 3, 5)
    assert normalize_box([1, 2, 3]) is None
    assert normalize_box([1, 2, "bad", 4]) is None


def test_vertical_overlap_ratio_uses_shorter_box_height() -> None:
    assert vertical_overlap_ratio((0, 10, 2, 30), (0, 20, 2, 40)) == 0.5
    assert vertical_overlap_ratio((0, 10, 2, 20), (0, 21, 2, 30)) == 0.0


def test_tolerant_match_count_is_one_to_one() -> None:
    historical = [(10, 0, 12, 100), (30, 0, 32, 100)]
    current = [(11, 0, 13, 100), (12, 0, 14, 100), (31, 0, 33, 100)]

    assert tolerant_match_count(historical, current) == 2


def test_tolerant_match_count_rejects_large_x_distance_or_low_overlap() -> None:
    historical = [(10, 0, 12, 100)]

    assert tolerant_match_count(historical, [(23, 0, 25, 100)]) == 0
    assert tolerant_match_count(historical, [(11, 80, 13, 180)]) == 0


def test_detection_path_matches_each_route_layout() -> None:
    root = Path("logs/issue245")
    image = Path("data/evaluation2/images/Score/page_001.png")

    assert detection_path(root, "run", image, in_process=True) == (
        root / "run/baseline/batch/page_001/page_001_detections.json"
    )
    assert detection_path(root, "run", image, in_process=False) == (
        root / "run/page_001/page_001_detections.json"
    )
