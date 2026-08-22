from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.common.thin_barline_finder import ThinBarlineConfig, detect_thin_vertical_runs


def test_preloaded_grayscale_bypasses_image_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.full((64, 64), 255, dtype=np.uint8)

    def fail_imread(*args, **kwargs):
        pytest.fail("preloaded grayscale must bypass cv2.imread")

    monkeypatch.setattr(cv2, "imread", fail_imread)
    assert (
        detect_thin_vertical_runs(
            Path("unused.png"),
            [],
            config=ThinBarlineConfig(vertical_gap_fill=0),
            grayscale_image=image,
        )
        == []
    )


def test_preloaded_grayscale_requires_two_dimensions() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="must be 2-D"):
        detect_thin_vertical_runs(
            Path("unused.png"),
            [],
            grayscale_image=image,
        )
