from __future__ import annotations

from src.measure_numbering.types import BBox, Staff
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    _identity_mapping_reliable,
)


def _staff(y1: int, y2: int) -> Staff:
    return Staff(bbox=BBox(0, y1, 1000, y2))


def test_identity_mapping_accepts_close_same_index_geometry() -> None:
    geometry = [_staff(100, 180), _staff(240, 320), _staff(500, 580)]
    semantic = [_staff(102, 182), _staff(238, 318), _staff(502, 582)]

    assert _identity_mapping_reliable(geometry, semantic) is True


def test_identity_mapping_rejects_shifted_index_correspondence() -> None:
    geometry = [_staff(100, 180), _staff(240, 320), _staff(500, 580)]
    semantic = [_staff(0, 40), _staff(100, 180), _staff(240, 320)]

    assert _identity_mapping_reliable(geometry, semantic) is False


def test_identity_mapping_rejects_equal_count_without_vertical_overlap() -> None:
    geometry = [_staff(100, 180), _staff(240, 320)]
    semantic = [_staff(400, 480), _staff(540, 620)]

    assert _identity_mapping_reliable(geometry, semantic) is False


def test_identity_mapping_rejects_count_mismatch() -> None:
    geometry = [_staff(100, 180), _staff(240, 320)]
    semantic = [_staff(100, 180)]

    assert _identity_mapping_reliable(geometry, semantic) is False
