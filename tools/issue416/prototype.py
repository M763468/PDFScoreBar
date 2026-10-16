"""Investigation-only geometry prototypes; production does not import this module.

Rules and constants define new experiments, not a new evaluation contract.
Connector masks remain separate inputs to production system construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import numpy as np

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class StaffRegion:
    bbox: Box
    unit_size: float

    def __post_init__(self) -> None:
        if not isfinite(self.unit_size) or self.unit_size <= 0:
            raise ValueError("Staff unit_size must be finite and positive")


def normalize_box(
    box: Box, staves: Sequence[StaffRegion], *, allow_single_tail: bool = False
) -> list[Box]:
    """Split multi-staff ink; opt-in single-tail clipping is a rejected ablation."""
    hits = [
        staff
        for staff in staves
        if min(box[3], staff.bbox[3]) - max(box[1], staff.bbox[1]) >= 2 * staff.unit_size
    ]
    overhang = bool(
        allow_single_tail
        and len(hits) == 1
        and (max(0, hits[0].bbox[1] - box[1]) + max(0, box[3] - hits[0].bbox[3]))
        >= 2 * hits[0].unit_size
    )
    if len(hits) < 2 and not overhang:
        return [box]
    return [(box[0], max(box[1], s.bbox[1]), box[2], min(box[3], s.bbox[3])) for s in hits]


def deduplicate_accepted(
    records: Sequence[dict], *, unit_size: float, preserve_geometry: bool = False
) -> tuple[list[dict], list[dict]]:
    """Ablate near-identical stroke boxes after CNN; preserve distinct strokes.

    The deliberately narrower 0.1unit X rule is independent of numbering's
    1.2unit logical-boundary merge. Kept records retain their actual CNN score.
    """
    if not isfinite(unit_size) or unit_size <= 0:
        raise ValueError("Page unit_size must be finite and positive")
    kept, removed = [], []

    def ordering(record):
        b = record["bbox"]
        if preserve_geometry:
            return (b[0], -(b[2] - b[0]), b[1], b[3], b[2], -record["score"])
        return (-record["score"], *b)

    for record in sorted(records, key=ordering):
        b = record["bbox"]
        duplicate = None
        for other in kept:
            a = other["bbox"]
            overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
            vov = overlap / max(1, a[3] - a[1], b[3] - b[1])
            xdist = abs((a[0] + a[2] - b[0] - b[2]) / 2)
            if vov >= 0.8 and xdist <= 0.1 * unit_size:
                duplicate = other
                break
        if duplicate is None:
            kept.append(record)
        else:
            removed.append(dict(record=record, representative=duplicate["bbox"]))
    return sorted(kept, key=lambda r: tuple(r["bbox"])), removed


def split_double_stroke(gray: np.ndarray, box: Box, *, unit_size: float) -> list[Box]:
    """Positive-hypothesis ablation using vertical ink runs, independent of GT."""
    if not isfinite(unit_size) or unit_size <= 0:
        raise ValueError("Page unit_size must be finite and positive")
    if box[3] - box[1] < 3 * unit_size:
        return [box]
    pad = int(round(0.5 * unit_size))
    x1, x2 = max(0, box[0] - pad), min(gray.shape[1], box[2] + pad)
    y1, y2 = max(0, box[1]), min(gray.shape[0], box[3])
    crop = gray[y1:y2, x1:x2]
    if not crop.size:
        return [box]
    columns = np.flatnonzero(np.mean(crop < 180, axis=0) >= 0.75)
    if not columns.size:
        return [box]
    runs = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    if len(runs) < 2:
        return [box]
    gaps = [right[0] - left[-1] - 1 for left, right in zip(runs, runs[1:])]
    if min(gaps) < 0.15 * unit_size:
        return [box]
    return [(x1 + int(r[0]), box[1], x1 + int(r[-1]) + 1, box[3]) for r in runs]
