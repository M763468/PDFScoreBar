"""Evidence for HOMR pages that return an empty detection result (#532).

HOMR stops with ``No noteheads found`` or ``No staffs found`` before it reaches the
connector (``brace_dot``) stage. The page-level runtime keeps the #62/#63 contract
and returns an empty result for such a page, but the log line alone cannot tell a
cover or blank page from a score page whose music HOMR failed to read. This module
records HOMR's own staff segmentation at the point of the empty result so that the
current x4 support stage can accept only pages without staff evidence as normal
empty pages, and fail explicitly for everything else.

The evidence is measured on HOMR's segmentation output, whose width HOMR normalises
before inference, inside a margin that excludes scan borders at the page edges.
Fractions are of the inner area and are therefore independent of the source DPI.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import numpy as np

EMPTY_DETECTION_REASONS = ("No noteheads found", "No staffs found")
EVIDENCE_SCHEMA_VERSION = "homr.empty_detection_evidence.v2"

# Fraction of the page height/width removed at each edge before measuring staff
# evidence. Scanned blank pages carry border lines there (Prokofiev Sym. 5 p6/p12).
EDGE_MARGIN_FRACTION = 0.05
# A page counts as a non-score page only when both bounds hold. They are calibrated
# on the production input of the current x4 route (x4 SR image, HOMR proxy), not on
# the original page: there, title text on a cover yields a dozen short "staff"
# fragments, so the fragment count is recorded but does not classify. Calibration
# table (evaluation2 cover/blank pages and synthetic staves without notes) is
# retained with Issue #532.
NON_SCORE_MAX_INNER_STAFF_FRACTION = 0.0005
NON_SCORE_MAX_INNER_ROW_STAFF_FRACTION = 0.05

NON_SCORE_PAGE = "non_score_page"
MUSIC_EVIDENCE_WITHOUT_DETECTIONS = "music_evidence_without_detections"
UNVERIFIED_EMPTY_RESULT = "unverified_empty_result"

_RECORDS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "pdfscore_homr_empty_detection_records",
    default=None,
)


class HomrEmptyDetectionError(RuntimeError):
    """HOMR found nothing to read; carries the segmentation evidence of the page.

    The message stays the HOMR reason so existing ``str(error)`` checks keep working.
    """

    def __init__(self, reason: str, evidence: Mapping[str, Any]) -> None:
        if reason not in EMPTY_DETECTION_REASONS:
            raise ValueError(f"Unknown HOMR empty-detection reason: {reason!r}")
        super().__init__(reason)
        self.reason = reason
        self.evidence = dict(evidence)


def _fragment_center(fragment: Any) -> tuple[float, float] | None:
    center = getattr(fragment, "center", None)
    if center is None:
        return None
    try:
        return float(center[0]), float(center[1])
    except (TypeError, IndexError, ValueError):
        return None


def segmentation_evidence(
    staff_mask: np.ndarray,
    staff_fragments: Sequence[Any],
    *,
    notehead_count: int,
) -> dict[str, Any]:
    """Measure staff evidence on one HOMR segmentation result."""

    staff = np.asarray(staff_mask) > 0
    if staff.ndim != 2 or staff.size == 0:
        raise ValueError(f"HOMR staff segmentation must be a non-empty 2-D mask: {staff.shape}")
    height, width = staff.shape
    margin_y = int(height * EDGE_MARGIN_FRACTION)
    margin_x = int(width * EDGE_MARGIN_FRACTION)
    inner = staff[margin_y : height - margin_y, margin_x : width - margin_x]

    inner_fragments = 0
    unlocated_fragments = 0
    for fragment in staff_fragments:
        center = _fragment_center(fragment)
        if center is None:
            unlocated_fragments += 1
            continue
        x, y = center
        if margin_x <= x < width - margin_x and margin_y <= y < height - margin_y:
            inner_fragments += 1

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "segmentation_shape_hw": [int(height), int(width)],
        "edge_margin_fraction": EDGE_MARGIN_FRACTION,
        "staff_mask_fraction": float(staff.mean()),
        "inner_staff_mask_fraction": float(inner.mean()) if inner.size else 0.0,
        # A staff line is a long horizontal run; text glyphs that HOMR marks as staff
        # fragments are short, so the widest single row separates the two.
        "inner_max_row_staff_fraction": float(inner.mean(axis=1).max()) if inner.size else 0.0,
        "staff_fragment_count": len(staff_fragments),
        "inner_staff_fragment_count": inner_fragments,
        "unlocated_staff_fragment_count": unlocated_fragments,
        "notehead_count": int(notehead_count),
    }


def classify_empty_detection(evidence: Mapping[str, Any] | None) -> str:
    """Classify an empty HOMR result from its recorded segmentation evidence."""

    if not evidence or evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return UNVERIFIED_EMPTY_RESULT
    try:
        inner_fraction = float(evidence["inner_staff_mask_fraction"])
        max_row = float(evidence["inner_max_row_staff_fraction"])
        unlocated = int(evidence["unlocated_staff_fragment_count"])
        noteheads = int(evidence["notehead_count"])
    except (KeyError, TypeError, ValueError):
        return UNVERIFIED_EMPTY_RESULT
    if (
        unlocated == 0
        and noteheads == 0
        and inner_fraction <= NON_SCORE_MAX_INNER_STAFF_FRACTION
        and max_row <= NON_SCORE_MAX_INNER_ROW_STAFF_FRACTION
    ):
        return NON_SCORE_PAGE
    return MUSIC_EVIDENCE_WITHOUT_DETECTIONS


def classification_thresholds() -> dict[str, Any]:
    return {
        "edge_margin_fraction": EDGE_MARGIN_FRACTION,
        "max_inner_staff_mask_fraction": NON_SCORE_MAX_INNER_STAFF_FRACTION,
        "max_inner_row_staff_fraction": NON_SCORE_MAX_INNER_ROW_STAFF_FRACTION,
        "max_notehead_count": 0,
    }


@contextmanager
def capture_empty_detections() -> Iterator[list[dict[str, Any]]]:
    """Collect empty-detection records emitted in the current execution context."""

    records: list[dict[str, Any]] = []
    token = _RECORDS.set(records)
    try:
        yield records
    finally:
        _RECORDS.reset(token)


def record_empty_detection(image_path: Path | str, error: BaseException) -> None:
    """Record one empty HOMR result; a no-op outside :func:`capture_empty_detections`."""

    records = _RECORDS.get()
    if records is None:
        return
    evidence = getattr(error, "evidence", None)
    records.append(
        {
            "image": str(image_path),
            "reason": str(error),
            "evidence": dict(evidence) if isinstance(evidence, Mapping) else None,
        }
    )
