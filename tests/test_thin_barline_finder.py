from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.common.thin_barline_finder import detect_thin_vertical_runs


@pytest.fixture()
def temp_image(tmp_path: Path) -> Path:
    return tmp_path / "page.png"


def _write_image(path: Path, array: np.ndarray) -> None:
    if not cv2.imwrite(str(path), array):
        raise RuntimeError(f"Failed to write test image to {path}")


def test_detects_isolated_thin_barline(temp_image: Path) -> None:
    image = np.full((120, 160), 255, dtype=np.uint8)
    image[40:64, 80:82] = 10
    _write_image(temp_image, image)

    extras = detect_thin_vertical_runs(temp_image, [])

    assert len(extras) == 1
    x1, y1, x2, y2 = extras[0]
    assert (x2 - x1) == 2
    assert (y2 - y1) >= 22


def test_accepts_barline_with_relaxed_adjacent_intensity(temp_image: Path) -> None:
    image = np.full((120, 160), 255, dtype=np.uint8)
    image[50:72, 90:91] = 40
    neighbour = image[50:72, 91:92]
    neighbour[:] = 170
    neighbour[2::6] = 255
    image[50:72, 92:95] = 245
    _write_image(temp_image, image)

    extras = detect_thin_vertical_runs(temp_image, [])

    assert any(box[0] == 90 for box in extras)


def test_rejects_note_stem_like_region(temp_image: Path) -> None:
    image = np.full((120, 160), 255, dtype=np.uint8)
    image[60:84, 40:42] = 15
    image[60:84, 42:45] = 40
    _write_image(temp_image, image)

    extras = detect_thin_vertical_runs(temp_image, [])

    assert extras == []
