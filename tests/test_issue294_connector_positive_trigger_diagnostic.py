from __future__ import annotations

from src.measure_numbering.types import BBox, Staff
from tools.issue294.diagnose_connector_positive_triggers import (
    _is_relaxed_trigger,
    _staff_mapping_metrics,
)


def test_relaxed_trigger_requires_positive_connector_and_missing_alignment() -> None:
    assert _is_relaxed_trigger(
        gap=100,
        avg_height=100,
        aligned_count=0,
        left_connector_present=True,
    )
    assert not _is_relaxed_trigger(
        gap=100,
        avg_height=100,
        aligned_count=2,
        left_connector_present=True,
    )
    assert not _is_relaxed_trigger(
        gap=100,
        avg_height=100,
        aligned_count=0,
        left_connector_present=False,
    )
    assert not _is_relaxed_trigger(
        gap=160,
        avg_height=100,
        aligned_count=0,
        left_connector_present=True,
    )


def test_staff_mapping_metrics_detect_same_index_pair() -> None:
    geometry = [
        Staff(bbox=BBox(0, 100, 1000, 180)),
        Staff(bbox=BBox(0, 240, 1000, 320)),
        Staff(bbox=BBox(0, 500, 1000, 580)),
    ]
    evidence = [
        Staff(bbox=BBox(0, 102, 1000, 182)),
        Staff(bbox=BBox(0, 238, 1000, 318)),
        Staff(bbox=BBox(0, 502, 1000, 582)),
    ]

    metrics = _staff_mapping_metrics(geometry, evidence, 0)

    assert metrics["same_index_is_best_for_pair"] is True
    assert metrics["best_evidence_indices_by_vertical_iou"] == [0, 1]
    assert min(metrics["same_index_vertical_iou"]) > 0.9


def test_staff_mapping_metrics_exposes_shifted_index_correspondence() -> None:
    geometry = [
        Staff(bbox=BBox(0, 100, 1000, 180)),
        Staff(bbox=BBox(0, 240, 1000, 320)),
        Staff(bbox=BBox(0, 500, 1000, 580)),
    ]
    evidence = [
        Staff(bbox=BBox(0, 0, 1000, 40)),
        Staff(bbox=BBox(0, 100, 1000, 180)),
        Staff(bbox=BBox(0, 240, 1000, 320)),
    ]

    metrics = _staff_mapping_metrics(geometry, evidence, 0)

    assert metrics["same_index_is_best_for_pair"] is False
    assert metrics["best_evidence_indices_by_vertical_iou"] == [1, 2]
