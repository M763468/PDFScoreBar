from __future__ import annotations

import numpy as np

from src.pipeline.probe_detector.bands import build_row_stats
from tools.issue245.analyze_probe_geometry_suppression import (
    MATRIX_IDS,
    SWEEP_VALUES,
    _inject,
    _remove,
    classify,
    run_variant,
)


def _target() -> dict[str, object]:
    return {"full_span": (10, 10, 14, 110), "short": (10, 50, 14, 110)}


def _matrix(**overrides: bool) -> dict[str, dict[str, object]]:
    return {name: {"exact_full_span_generated": overrides.get(name, False)} for name in MATRIX_IDS}


def test_historical_and_current_row_stats_are_independent() -> None:
    historical = build_row_stats([(1, 10, 3, 110)], cluster_max_dist=25.0, min_row_count=1)
    current = build_row_stats([(1, 50, 3, 150)], cluster_max_dist=25.0, min_row_count=1)

    assert historical != current
    assert historical[0]["top"] == 10.0
    assert current[0]["top"] == 50.0


def test_explicit_row_stats_remain_fixed_when_existing_boxes_change() -> None:
    calls: list[dict[str, object]] = []

    def fake_detect(**kwargs: object) -> list[tuple[int, int, int, int]]:
        calls.append(kwargs)
        return [(10, 10, 14, 110)]

    image = np.zeros((200, 200, 3), dtype=np.uint8)
    fixed = build_row_stats([(1, 10, 3, 110)], cluster_max_dist=25.0, min_row_count=1)
    run_variant(
        image=image,
        existing_boxes=[(1, 10, 3, 110)],
        row_stats=fixed,
        targets=[_target()],
        suppression=True,
        detect_fn=fake_detect,
    )
    run_variant(
        image=image,
        existing_boxes=[(1, 80, 3, 180)],
        row_stats=fixed,
        targets=[_target()],
        suppression=True,
        detect_fn=fake_detect,
    )

    assert calls[0]["row_stats"] == calls[1]["row_stats"] == fixed


def test_matrix_ids_cover_all_band_existing_suppression_combinations() -> None:
    assert set(MATRIX_IDS) == {
        "HH-on",
        "HC-on",
        "CH-on",
        "CC-on",
        "HH-off",
        "HC-off",
        "CH-off",
        "CC-off",
    }


def test_remove_short_changes_only_requested_bbox() -> None:
    boxes = [(1, 1, 2, 2), (10, 50, 14, 110), (20, 1, 22, 2)]

    assert _remove(boxes, [(10, 50, 14, 110)]) == [(1, 1, 2, 2), (20, 1, 22, 2)]


def test_inject_short_deduplicates_existing_bbox() -> None:
    boxes = [(1, 1, 2, 2), (10, 50, 14, 110)]

    assert _inject(boxes, [(10, 50, 14, 110)]) == sorted(boxes)


def test_vertical_iou_sweep_values_include_default_and_requested_levels() -> None:
    assert SWEEP_VALUES == (0.0, 0.5, 0.55, 0.6, 0.65, 0.75)


def test_classifies_existing_suppression_only() -> None:
    ablations = {"current_frozen_remove_short_1": {"exact_full_span_generated": True}}

    assert classify(_matrix(**{"CC-off": True}), ablations) == "existing_suppression_only"


def test_classifies_row_band_geometry_only() -> None:
    assert classify(_matrix(**{"HC-off": True}), {}) == "row_band_geometry_only"


def test_classifies_combined_case() -> None:
    assert classify(_matrix(**{"CC-off": True}), {}) == "combined_band_and_suppression"


def test_generated_candidates_are_not_merged_with_existing_boxes() -> None:
    image = np.zeros((200, 200, 3), dtype=np.uint8)

    def fake_detect(**_: object) -> list[tuple[int, int, int, int]]:
        return [(10, 10, 14, 110)]

    generated, _ = run_variant(
        image=image,
        existing_boxes=[(50, 10, 54, 110)],
        row_stats=build_row_stats([(50, 10, 54, 110)], cluster_max_dist=25.0, min_row_count=1),
        targets=[_target()],
        suppression=False,
        detect_fn=fake_detect,
    )

    assert generated == [(10, 10, 14, 110)]
