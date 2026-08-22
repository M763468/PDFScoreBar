"""Experiment: reuse current-HOMR's decoded x4 BGR image for thin-barline grayscale."""

from __future__ import annotations

from pathlib import Path

import cv2

from src.pipeline.detection import current_homr_worker


_ORIGINAL_IMREAD = cv2.imread
_CACHE: dict[str, object] = {}


def _resolved(path: str) -> str:
    return str(Path(path).resolve())


def _reuse_imread(path: str, flags: int = cv2.IMREAD_COLOR):
    key = _resolved(path)
    if flags == cv2.IMREAD_GRAYSCALE:
        cached = _CACHE.get(key)
        if cached is not None:
            return cv2.cvtColor(cached, cv2.COLOR_BGR2GRAY)

    image = _ORIGINAL_IMREAD(path, flags)
    if image is not None and flags == cv2.IMREAD_COLOR:
        _CACHE[key] = image
    return image


def main() -> int:
    cv2.imread = _reuse_imread
    try:
        return current_homr_worker.main()
    finally:
        cv2.imread = _ORIGINAL_IMREAD
        _CACHE.clear()


if __name__ == "__main__":
    raise SystemExit(main())
