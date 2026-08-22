"""Experiment: reuse current-HOMR's decoded x4 BGR image for thin-barline grayscale."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from src.pipeline.detection import current_homr_worker
from src.pipeline.perf_trace import span

_ORIGINAL_IMREAD = cv2.imread
_ORIGINAL_MORPHOLOGY_EX = cv2.morphologyEx
_TARGET_KEY: str | None = None
_TARGET_BGR: np.ndarray | None = None


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
        "current_homr.post.thin_barline.extract_runs", originals["extract"]
    )
    thin_barline_finder._find_double_pairs = _timed(
        "current_homr.post.thin_barline.find_double_pairs", originals["pairs"]
    )
    thin_barline_finder._filter_candidates = _timed(
        "current_homr.post.thin_barline.filter_candidates", originals["filter"]
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
