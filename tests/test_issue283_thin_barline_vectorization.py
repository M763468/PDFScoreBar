from __future__ import annotations

import numpy as np
import pytest

from src.common.thin_barline_finder import _extract_vertical_runs


def _legacy_extract_vertical_runs(
    binary: np.ndarray,
    *,
    min_height: int,
    max_height: int,
) -> list[tuple[int, int, int]]:
    height, width = binary.shape
    runs: list[tuple[int, int, int]] = []
    min_height_relaxed = max(min_height - 1, 1)
    for x in range(width):
        column = binary[:, x]
        y = 0
        while y < height:
            while y < height and column[y] == 0:
                y += 1
            if y >= height:
                break
            start = y
            while y < height and column[y]:
                y += 1
            run_height = y - start
            if min_height <= run_height <= max_height:
                runs.append((x, start, y))
            elif min_height_relaxed <= run_height <= max_height:
                runs.append((x, start, y))
    return runs


@pytest.mark.parametrize("seed", range(12))
def test_vectorized_run_extraction_matches_legacy_randomized(seed: int) -> None:
    rng = np.random.default_rng(seed)
    binary = (rng.random((97, 53)) < 0.18).astype(np.uint8)

    # Add longer runs, including top/bottom edge cases and runs near the relaxed
    # min-height boundary.  Values other than 1 verify legacy truthiness.
    for _ in range(20):
        x = int(rng.integers(0, binary.shape[1]))
        y1 = int(rng.integers(0, binary.shape[0] - 1))
        length = int(rng.integers(1, 30))
        y2 = min(binary.shape[0], y1 + length)
        binary[y1:y2, x] = int(rng.choice([1, 2, 255]))
    binary[:17, 0] = 1
    binary[-24:, -1] = 1

    expected = _legacy_extract_vertical_runs(binary, min_height=18, max_height=24)
    actual = _extract_vertical_runs(binary, min_height=18, max_height=24)

    assert actual == expected


@pytest.mark.parametrize(
    ("min_height", "max_height"),
    [
        (1, 1),
        (2, 2),
        (18, 24),
        (32, 64),
    ],
)
def test_vectorized_run_extraction_matches_legacy_boundaries(
    min_height: int,
    max_height: int,
) -> None:
    binary = np.zeros((80, 8), dtype=np.uint8)
    lengths = [1, max(min_height - 1, 1), min_height, max_height, min(max_height + 1, 80)]
    for x, length in enumerate(lengths):
        binary[:length, x] = 1
    binary[20:40, 6] = 1
    binary[50:, 7] = 1

    assert _extract_vertical_runs(
        binary, min_height=min_height, max_height=max_height
    ) == _legacy_extract_vertical_runs(
        binary, min_height=min_height, max_height=max_height
    )


def test_vectorized_run_extraction_rejects_non_2d_input() -> None:
    with pytest.raises(ValueError, match="must be 2-D"):
        _extract_vertical_runs(np.zeros((2, 3, 4), dtype=np.uint8), min_height=1, max_height=2)
