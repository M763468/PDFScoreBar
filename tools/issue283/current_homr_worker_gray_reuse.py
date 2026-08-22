"""Experiment: reuse x4 decode and vectorize residual thin-barline hot paths."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

import cv2
import numpy as np

from src.common import Box
from src.pipeline.detection import current_homr_worker
from src.pipeline.perf_trace import span

_ORIGINAL_IMREAD = cv2.imread
_ORIGINAL_MORPHOLOGY_EX = cv2.morphologyEx
_TARGET_KEY: str | None = None
_TARGET_BGR: np.ndarray | None = None
_RUN_X_BLOCK = 64
_PAIR_OUTER_CHUNK = 1024


def _resolved(path: str | Path) -> str:
    return str(Path(path).resolve())


def _request_sr_image() -> str:
    try:
        request_index = sys.argv.index("--request") + 1
        request_path = Path(sys.argv[request_index])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("Gray-reuse experiment requires --request") from exc
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    return _resolved(str(payload["sr_image"]))


def _reuse_imread(path: str, flags: int = cv2.IMREAD_COLOR):
    global _TARGET_BGR

    key = _resolved(path)
    if key == _TARGET_KEY:
        if flags == cv2.IMREAD_GRAYSCALE and _TARGET_BGR is not None:
            with span("current_homr.post.thin_barline.gray_from_cached_bgr"):
                return cv2.cvtColor(_TARGET_BGR, cv2.COLOR_BGR2GRAY)
        if flags == cv2.IMREAD_COLOR:
            image = _ORIGINAL_IMREAD(path, flags)
            if image is not None:
                _TARGET_BGR = image
            return image
    return _ORIGINAL_IMREAD(path, flags)


def _extract_vertical_runs_chunked(
    binary: np.ndarray,
    *,
    min_height: int,
    max_height: int,
) -> list[tuple[int, int, int]]:
    """Exact run extraction using cache-sized x blocks instead of one 200MP temporary."""

    if binary.ndim != 2:
        raise ValueError(f"Thin-barline binary image must be 2-D, got {binary.shape}")
    if max_height < 1:
        return []

    min_height_relaxed = max(min_height - 1, 1)
    width = binary.shape[1]
    runs: list[tuple[int, int, int]] = []
    for x_offset in range(0, width, _RUN_X_BLOCK):
        x_end = min(width, x_offset + _RUN_X_BLOCK)
        active_xy = (binary[:, x_offset:x_end] != 0).T
        padded = np.pad(
            active_xy,
            ((0, 0), (1, 1)),
            mode="constant",
            constant_values=False,
        )
        edge_x, edge_y = np.nonzero(padded[:, 1:] != padded[:, :-1])
        if edge_x.size == 0:
            continue
        if edge_x.size % 2:
            raise RuntimeError("Unbalanced thin-barline vertical run transitions")

        start_x = edge_x[0::2]
        start_y = edge_y[0::2]
        end_x = edge_x[1::2]
        end_y = edge_y[1::2]
        if start_x.shape != end_x.shape or not np.array_equal(start_x, end_x):
            raise RuntimeError("Unbalanced thin-barline vertical run transitions")

        run_heights = end_y - start_y
        keep = (run_heights >= min_height_relaxed) & (run_heights <= max_height)
        runs.extend(
            (int(x_offset + x), int(y1), int(y2))
            for x, y1, y2 in zip(start_x[keep], start_y[keep], end_y[keep])
        )
    return runs


def _find_double_pairs_chunked(merged: Sequence[Box], *, cfg) -> set[Box]:
    """Exact double-pair membership using bounded vectorized candidate chunks."""

    if len(merged) < 2 or cfg.double_pair_max_gap <= 0:
        return set()

    boxes = np.asarray(merged, dtype=np.int64)
    count = len(boxes)
    starts = boxes[:, 0]
    widths = boxes[:, 2] - boxes[:, 0]
    heights = boxes[:, 3] - boxes[:, 1]
    eligible = (widths <= cfg.double_pair_max_width) & (
        heights >= cfg.double_pair_min_height
    )
    paired = np.zeros(count, dtype=bool)
    indices = np.arange(count, dtype=np.int64)

    for chunk_start in range(0, count - 1, _PAIR_OUTER_CHUNK):
        chunk_end = min(count - 1, chunk_start + _PAIR_OUTER_CHUNK)
        outer = indices[chunk_start:chunk_end]
        first = np.searchsorted(starts, boxes[outer, 2], side="right")
        last = np.searchsorted(
            starts,
            boxes[outer, 2] + cfg.double_pair_max_gap,
            side="right",
        )
        lengths = last - first
        lengths = np.where(eligible[outer], lengths, 0)
        total = int(lengths.sum())
        if total == 0:
            continue

        left_indices = np.repeat(outer, lengths)
        offsets = np.cumsum(lengths, dtype=np.int64) - lengths
        right_indices = np.arange(total, dtype=np.int64) + np.repeat(first - offsets, lengths)

        right_eligible = eligible[right_indices]
        if not np.any(right_eligible):
            continue
        left_indices = left_indices[right_eligible]
        right_indices = right_indices[right_eligible]

        overlap = np.minimum(boxes[left_indices, 3], boxes[right_indices, 3]) - np.maximum(
            boxes[left_indices, 1], boxes[right_indices, 1]
        )
        valid = (overlap > 0) & (
            overlap.astype(np.float64)
            / np.maximum(heights[left_indices], heights[right_indices])
            >= cfg.double_pair_min_overlap
        )
        if np.any(valid):
            paired[left_indices[valid]] = True
            paired[right_indices[valid]] = True

    return {
        tuple(int(value) for value in boxes[index])
        for index in np.flatnonzero(paired)
    }


def _timed(stage: str, function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with span(stage):
            return function(*args, **kwargs)

    return wrapper


def _timed_morphology_ex(src, op, kernel, *args, **kwargs):
    target_shape = None if _TARGET_BGR is None else _TARGET_BGR.shape[:2]
    if target_shape is not None and src.ndim == 2 and src.shape == target_shape:
        with span("current_homr.post.thin_barline.morphology_close"):
            return _ORIGINAL_MORPHOLOGY_EX(src, op, kernel, *args, **kwargs)
    return _ORIGINAL_MORPHOLOGY_EX(src, op, kernel, *args, **kwargs)


def main() -> int:
    global _TARGET_KEY, _TARGET_BGR

    from src.common import thin_barline_finder

    originals = {
        "extract": thin_barline_finder._extract_vertical_runs,
        "pairs": thin_barline_finder._find_double_pairs,
        "filter": thin_barline_finder._filter_candidates,
    }
    thin_barline_finder._extract_vertical_runs = _timed(
        "current_homr.post.thin_barline.extract_runs",
        _extract_vertical_runs_chunked,
    )
    thin_barline_finder._find_double_pairs = _timed(
        "current_homr.post.thin_barline.find_double_pairs",
        _find_double_pairs_chunked,
    )
    thin_barline_finder._filter_candidates = _timed(
        "current_homr.post.thin_barline.filter_candidates",
        originals["filter"],
    )

    _TARGET_KEY = _request_sr_image()
    cv2.imread = _reuse_imread
    cv2.morphologyEx = _timed_morphology_ex
    try:
        return current_homr_worker.main()
    finally:
        cv2.imread = _ORIGINAL_IMREAD
        cv2.morphologyEx = _ORIGINAL_MORPHOLOGY_EX
        thin_barline_finder._extract_vertical_runs = originals["extract"]
        thin_barline_finder._find_double_pairs = originals["pairs"]
        thin_barline_finder._filter_candidates = originals["filter"]
        _TARGET_BGR = None
        _TARGET_KEY = None


if __name__ == "__main__":
    raise SystemExit(main())
