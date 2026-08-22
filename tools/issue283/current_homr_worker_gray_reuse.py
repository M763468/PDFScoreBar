"""Experiment: reuse current-HOMR's decoded x4 BGR image for thin-barline grayscale."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.detection import current_homr_worker

_ORIGINAL_IMREAD = cv2.imread
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
            return cv2.cvtColor(_TARGET_BGR, cv2.COLOR_BGR2GRAY)
        if flags == cv2.IMREAD_COLOR:
            image = _ORIGINAL_IMREAD(path, flags)
            if image is not None:
                _TARGET_BGR = image
            return image
    return _ORIGINAL_IMREAD(path, flags)


def main() -> int:
    global _TARGET_KEY, _TARGET_BGR

    _TARGET_KEY = _request_sr_image()
    cv2.imread = _reuse_imread
    try:
        return current_homr_worker.main()
    finally:
        cv2.imread = _ORIGINAL_IMREAD
        _TARGET_BGR = None
        _TARGET_KEY = None


if __name__ == "__main__":
    raise SystemExit(main())
