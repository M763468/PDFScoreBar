from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from tools.issue255.analyze_public_stage_e_sr_reconstruction_gap import (
    _find_sr_image,
    _image_comparison,
    _page_classification,
    _scaled_box,
)


def _write_image(path: Path, value: int, shape: tuple[int, int] = (8, 12)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full(shape, value, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def test_find_sr_image_prefers_exact_page_image(tmp_path: Path) -> None:
    detection = tmp_path / "sr" / "batch" / "page_004" / "page_004_detections.json"
    detection.parent.mkdir(parents=True)
    detection.write_text("[]", encoding="utf-8")
    expected = detection.parent / "page_004.png"
    _write_image(expected, 255)
    _write_image(detection.parent / "page_004_staff_mask.png", 0)

    assert _find_sr_image(detection, "page_004") == expected.resolve()


def test_image_comparison_classifies_byte_exact_and_changed(tmp_path: Path) -> None:
    historical = tmp_path / "historical.png"
    public = tmp_path / "public.png"
    _write_image(historical, 255)
    _write_image(public, 255)

    exact = _image_comparison(historical, public)
    assert exact["classification"] == "sr_images_byte_exact"
    assert exact["changed_pixel_ratio"] == 0.0

    changed_image = np.full((8, 12), 255, dtype=np.uint8)
    changed_image[0, 0] = 0
    assert cv2.imwrite(str(public), changed_image)
    changed = _image_comparison(historical, public)
    assert changed["classification"] == "sr_image_generation_differs"
    assert changed["changed_pixel_ratio"] > 0.0


def test_scaled_box_uses_independent_axes() -> None:
    assert _scaled_box([10, 20, 14, 120], scale_x=2.0, scale_y=1.5) == (
        20,
        30,
        28,
        180,
    )


def test_page_classification_uses_sr_image_boundary() -> None:
    consensus = "current_consensus_reproduces_both_from_component_inputs"

    assert (
        _page_classification(
            consensus_classification=consensus,
            image_comparison={"classification": "sr_image_generation_differs"},
        )
        == "sr_image_generation_is_first_unresolved_boundary"
    )
    assert (
        _page_classification(
            consensus_classification=consensus,
            image_comparison={"classification": "sr_images_byte_exact"},
        )
        == "sr_detector_or_runtime_differs_on_same_sr_image"
    )
