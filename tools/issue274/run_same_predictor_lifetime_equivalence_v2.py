#!/usr/bin/env python3
"""Shape-safe wrapper for the Issue #274 same-predictor lifetime gate.

The original focused runner correctly detected a mask-shape mismatch but its
shape-mismatch comparison payload omitted the ``binary_exact`` key consumed by
the gate, causing a KeyError before the comparison could be reported.  This
wrapper preserves the original experiment while making shape mismatches a
first-class comparison result and recording scale-normalized diagnostics.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue274 import run_same_predictor_lifetime_equivalence as base  # noqa: E402


def _binary_iou(left: np.ndarray, right: np.ndarray) -> float:
    left_binary = left > 0
    right_binary = right > 0
    union = np.logical_or(left_binary, right_binary)
    if not np.count_nonzero(union):
        return 1.0
    intersection = np.logical_and(left_binary, right_binary)
    return float(np.count_nonzero(intersection)) / float(np.count_nonzero(union))


def _shape_ratio(shape: tuple[int, ...], other: tuple[int, ...]) -> list[float] | None:
    if len(shape) != len(other) or any(value == 0 for value in other):
        return None
    return [float(value) / float(reference) for value, reference in zip(shape, other)]


def _compare_mask_files_shape_safe(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = base._load_mask(left_path)  # noqa: SLF001
    right = base._load_mask(right_path)  # noqa: SLF001

    if left.shape == right.shape:
        return base._compare_mask_files(left_path, right_path)  # noqa: SLF001

    # Preserve all keys consumed by the existing gates and add diagnostics that
    # distinguish a coordinate-space/resize mismatch from a genuinely different
    # mask.  INTER_NEAREST is appropriate because these are categorical masks.
    right_to_left = cv2.resize(
        right,
        (int(left.shape[1]), int(left.shape[0])),
        interpolation=cv2.INTER_NEAREST,
    )
    left_to_right = cv2.resize(
        left,
        (int(right.shape[1]), int(right.shape[0])),
        interpolation=cv2.INTER_NEAREST,
    )

    return {
        "left": str(left_path),
        "right": str(right_path),
        "left_file_sha256": base._sha256_file(left_path),  # noqa: SLF001
        "right_file_sha256": base._sha256_file(right_path),  # noqa: SLF001
        "left_array_sha256": base._sha256_array(left),  # noqa: SLF001
        "right_array_sha256": base._sha256_array(right),  # noqa: SLF001
        "left_shape": list(left.shape),
        "right_shape": list(right.shape),
        "left_nonzero": int(np.count_nonzero(left)),
        "right_nonzero": int(np.count_nonzero(right)),
        "shape_equal": False,
        "array_exact": False,
        "binary_exact": False,
        "binary_iou": None,
        "different_pixels": None,
        "different_binary_pixels": None,
        "difference_bbox": None,
        "row_projection_exact": False,
        "column_projection_exact": False,
        "left_over_right_shape_ratio": _shape_ratio(left.shape, right.shape),
        "right_over_left_shape_ratio": _shape_ratio(right.shape, left.shape),
        "right_resized_to_left_binary_iou": _binary_iou(left, right_to_left),
        "left_resized_to_right_binary_iou": _binary_iou(left_to_right, right),
        "diagnosis": "mask_shape_mismatch",
    }


def main() -> int:
    base._compare_mask_files = _compare_mask_files_shape_safe  # type: ignore[attr-defined]  # noqa: SLF001
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
