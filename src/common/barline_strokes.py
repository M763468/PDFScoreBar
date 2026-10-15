"""Staff-local stroke geometry; connector evidence and GT matching stay separate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .barline_geometry import Box, barline_vertical_overlap


@dataclass(frozen=True)
class StaffRegion:
    bbox: Box
    unit_size: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.unit_size) or self.unit_size <= 0:
            raise ValueError("Staff unit_size must be finite and positive")


def normalize_staff_stroke(box: Box, staves: Sequence[StaffRegion]) -> list[tuple[int, Box]]:
    """Split only boxes spanning two or more substantial staff intersections.

    A connector tail intersecting just one staff remains unchanged. Rough staff
    envelopes alone cannot establish the stroke extent of that case.
    """
    hits = [
        (index, staff)
        for index, staff in enumerate(staves)
        if min(box[3], staff.bbox[3]) - max(box[1], staff.bbox[1]) >= 2 * staff.unit_size
    ]
    if len(hits) < 2:
        return [(-1, box)]
    return [
        (index, (box[0], max(box[1], staff.bbox[1]), box[2], min(box[3], staff.bbox[3])))
        for index, staff in hits
    ]


def deduplicate_staff_strokes(
    records: Sequence[dict[str, Any]], *, unit_size: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep canonical geometry and each representative's own actual CNN score.

    The 0.1-unit stroke tolerance is deliberately separate from numbering's
    1.2-unit logical time-boundary merge. Vertical overlap keeps voices separate.
    """
    if not math.isfinite(unit_size) or unit_size <= 0:
        raise ValueError("Stroke deduplication requires finite positive staff units")

    def order(record):
        b = record["bbox"]
        return (b[0], -(b[2] - b[0]), b[1], b[3], b[2], -record["score"])

    kept, suppressed = [], []
    for record in sorted(records, key=order):
        box = record["bbox"]
        representative = next(
            (
                item
                for item in kept
                if abs(sum(item["bbox"][::2]) - sum(box[::2])) / 2 <= 0.1 * unit_size
                and barline_vertical_overlap(item["bbox"], box) >= 0.8
            ),
            None,
        )
        if representative is None:
            kept.append(record)
        else:
            suppressed.append({"bbox": box, "representative": representative["bbox"]})
    return sorted(kept, key=lambda item: tuple(item["bbox"])), suppressed
