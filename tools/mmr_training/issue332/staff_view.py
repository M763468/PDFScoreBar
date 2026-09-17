"""Source-page staff-relative classifier views for Issue #332."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np

STAFF_CORE_CENTER_VIEW = "staff-core-center-3h"
STAFF_CORE_CENTER_WIDTH_RATIO = 3.0


def _validated_bbox(raw: Sequence[float]) -> tuple[float, float, float, float]:
    if len(raw) != 4:
        raise ValueError(f"bbox must contain four coordinates, got {raw!r}")
    values = tuple(float(value) for value in raw)
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"bbox contains non-finite values: {raw!r}")
    if values[2] <= values[0] or values[3] <= values[1]:
        raise ValueError(f"bbox must have positive area: {raw!r}")
    return values


@lru_cache(maxsize=128)
def _load_numbering_staves(numbering_path: str, system_index: int) -> tuple[tuple[float, ...], ...]:
    payload = json.loads(Path(numbering_path).read_text(encoding="utf-8"))
    pages = payload.get("pages", [])
    if not pages or system_index < 0 or system_index >= len(pages[0].get("systems", [])):
        raise ValueError(f"invalid system index {system_index} in numbering file {numbering_path}")
    staves = pages[0]["systems"][system_index].get("staves", [])
    if not staves:
        raise ValueError(f"system {system_index} has no staves in {numbering_path}")
    return tuple(_validated_bbox(stave["bbox"]) for stave in staves)


def source_staff_bboxes(sample: dict[str, Any]) -> tuple[tuple[float, ...], ...]:
    """Resolve source numbering staff bboxes without using perturbed geometry."""
    cached = sample.get("_staff_bboxes")
    if cached is not None:
        return tuple(tuple(float(value) for value in bbox) for bbox in cached)
    explicit = sample.get("staff_bboxes")
    if explicit is not None:
        return tuple(_validated_bbox(bbox) for bbox in explicit)
    provenance = sample.get("provenance", {})
    numbering_path = provenance.get("numbering_path")
    system_index = sample.get("system_index")
    if not numbering_path or system_index is None:
        raise ValueError(
            f"sample {sample.get('sample_id')} lacks source numbering_path/system_index"
        )
    return _load_numbering_staves(str(Path(numbering_path).resolve()), int(system_index))


def staff_relative_roi_bboxes(
    sample: dict[str, Any],
    measure_bbox: Sequence[float] | None = None,
    *,
    width_ratio: float = STAFF_CORE_CENTER_WIDTH_RATIO,
) -> tuple[tuple[float, float, float, float], ...]:
    """Return one center-window staff-core ROI per source staff.

    The measure bbox may be a source-space perturbation. Staff bboxes always
    come from the canonical source numbering artifact and are never shifted or
    resized from the perturbed measure geometry.
    """
    if width_ratio <= 0:
        raise ValueError("width_ratio must be positive")
    mx1, my1, mx2, my2 = _validated_bbox(measure_bbox or sample["bbox"])
    center_x = (mx1 + mx2) / 2.0
    result = []
    for sx1, sy1, sx2, sy2 in source_staff_bboxes(sample):
        staff_height = sy2 - sy1
        half_width = width_ratio * staff_height / 2.0
        rx1 = max(mx1, center_x - half_width)
        rx2 = min(mx2, center_x + half_width)
        if rx2 <= rx1:
            raise ValueError(f"empty staff-relative ROI for sample {sample.get('sample_id')}")
        result.append((rx1, sy1, rx2, sy2))
    return tuple(result)


def crop_source_bbox(image: np.ndarray, bbox: Sequence[float]) -> np.ndarray:
    """Crop a source-page bbox without a fixed margin."""
    x1, y1, x2, y2 = _validated_bbox(bbox)
    height, width = image.shape[:2]
    cx1 = max(0, int(x1))
    cy1 = max(0, int(y1))
    cx2 = min(width, int(x2))
    cy2 = min(height, int(y2))
    if cx2 <= cx1 or cy2 <= cy1:
        raise ValueError(f"empty source crop for bbox={bbox!r} and image={width}x{height}")
    crop = image[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        raise ValueError(f"empty source crop for bbox={bbox!r}")
    return crop


def staff_view_contract() -> dict[str, Any]:
    return {
        "view": STAFF_CORE_CENTER_VIEW,
        "staff_count": "variable; one crop per source-numbering staff",
        "x": "[max(measure_x1, center_x - 1.5*h), min(measure_x2, center_x + 1.5*h)]",
        "center_x": "(measure_x1 + measure_x2) / 2",
        "y": "[staff_y1, staff_y2]",
        "h": "staff_y2 - staff_y1",
        "width": "min(measure_width, 3*h)",
        "margin_px": 0,
        "staff_bbox_source": "canonical source numbering system['staves'][*]['bbox']",
        "perturbation_rule": (
            "if measure bbox is perturbed, recompute center/window from perturbed measure bbox; "
            "keep source staff bbox fixed"
        ),
        "future_acceptance_caveat": (
            "measure translate-y perturbation does not move the staff ROI; future acceptance must "
            "also evaluate independent source staff-bbox +/-1/2/4px sensitivity"
        ),
    }
