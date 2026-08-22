from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.common.thin_barline_finder import _extract_vertical_runs, _find_double_pairs
from tools.issue283.current_homr_worker_gray_reuse import (
    _extract_vertical_runs_chunked,
    _find_double_pairs_chunked,
)


@pytest.mark.parametrize("seed", range(12))
def test_chunked_run_extraction_matches_stage2(seed: int) -> None:
    rng = np.random.default_rng(seed)
    binary = rng.integers(0, 5, size=(193, 137), dtype=np.uint8)
    binary[rng.random(binary.shape) < 0.72] = 0

    for _ in range(40):
        x = int(rng.integers(0, binary.shape[1]))
        y1 = int(rng.integers(0, binary.shape[0]))
        length = int(rng.integers(1, 80))
        y2 = min(binary.shape[0], y1 + length)
        binary[y1:y2, x] = int(rng.choice([1, 2, 255]))

    expected = _extract_vertical_runs(binary, min_height=18, max_height=64)
    actual = _extract_vertical_runs_chunked(binary, min_height=18, max_height=64)
    assert actual == expected


@pytest.mark.parametrize(
    ("shape", "min_height", "max_height"),
    [
        ((0, 0), 1, 1),
        ((1, 1), 1, 1),
        ((80, 8), 18, 24),
        ((80, 129), 18, 64),
    ],
)
def test_chunked_run_extraction_matches_stage2_boundaries(
    shape: tuple[int, int], min_height: int, max_height: int
) -> None:
    binary = np.zeros(shape, dtype=np.uint8)
    if binary.size:
        binary[:, 0] = 1
        binary[max(0, shape[0] // 3) :, -1] = 255
    assert _extract_vertical_runs_chunked(
        binary, min_height=min_height, max_height=max_height
    ) == _extract_vertical_runs(binary, min_height=min_height, max_height=max_height)


def _random_merged(seed: int) -> list[tuple[int, int, int, int]]:
    rng = np.random.default_rng(seed)
    boxes: list[tuple[int, int, int, int]] = []
    for _ in range(400):
        x1 = int(rng.integers(0, 120))
        width = int(rng.integers(1, 10))
        y1 = int(rng.integers(0, 400))
        height = int(rng.integers(5, 100))
        boxes.append((x1, y1, x1 + width, y1 + height))
    boxes.sort()
    return boxes


@pytest.mark.parametrize("seed", range(16))
def test_chunked_double_pair_membership_matches_stage2(seed: int) -> None:
    merged = _random_merged(seed)
    cfg = SimpleNamespace(
        double_pair_max_gap=6,
        double_pair_min_overlap=0.75,
        double_pair_min_height=18,
        double_pair_max_width=6,
    )
    assert _find_double_pairs_chunked(merged, cfg=cfg) == _find_double_pairs(merged, cfg=cfg)


@pytest.mark.parametrize("max_gap", [0, -1])
def test_chunked_double_pair_nonpositive_gap_is_empty(max_gap: int) -> None:
    merged = [(0, 0, 1, 20), (2, 0, 3, 20)]
    cfg = SimpleNamespace(
        double_pair_max_gap=max_gap,
        double_pair_min_overlap=0.75,
        double_pair_min_height=18,
        double_pair_max_width=6,
    )
    assert _find_double_pairs_chunked(merged, cfg=cfg) == _find_double_pairs(merged, cfg=cfg)
