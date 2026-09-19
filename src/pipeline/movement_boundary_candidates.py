"""Conservative movement-boundary review candidate generation.

This module produces evidence only. It never exports resolved Issue #268
numbering resets and never assigns an automatic confidence.
"""

from __future__ import annotations

import re
from copy import deepcopy
from statistics import median
from typing import Any, Mapping, Sequence

EVIDENCE_SCHEMA_VERSION = "issue333.movement_boundary_evidence.v1"
PRODUCER_NAME = "pdfscorebar.geometry_movement_boundary_candidates"
PRODUCER_VERSION = "2"
DEFAULT_INDENT_RATIO = 0.02
DEFAULT_GAP_RATIO = 1.75


def _system_box(system: Mapping[str, Any]) -> tuple[float, float, float, float]:
    staves = system.get("staves")
    if not isinstance(staves, list) or not staves:
        raise ValueError("movement candidate systems require at least one staff")
    boxes = []
    for staff in staves:
        if not isinstance(staff, Mapping):
            raise ValueError("movement candidate staff must be an object")
        bbox = staff.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("movement candidate staff bbox must contain four coordinates")
        values = tuple(float(value) for value in bbox)
        if values[2] <= values[0] or values[3] <= values[1]:
            raise ValueError("movement candidate staff bbox must have positive area")
        boxes.append(values)
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _page_reference(
    manifest_page: Mapping[str, Any] | None, *, source_document_sha256: str
) -> dict[str, Any]:
    if manifest_page is None:
        return {}
    page_id = manifest_page.get("page_id")
    image_path = manifest_page.get("image_path")
    reference = {}
    if isinstance(page_id, str) and page_id:
        reference["page_id"] = page_id
    source_reference = manifest_page.get("source_reference")
    if isinstance(source_reference, Mapping):
        kind = source_reference.get("kind")
        if kind == "direct_pdf_render":
            source_page = source_reference.get("source_page")
            if not isinstance(source_page, int) or isinstance(source_page, bool) or source_page < 0:
                raise ValueError(
                    "direct_pdf_render source_reference.source_page must be a nonnegative integer"
                )
            source_document = source_reference.get("source_document")
            digest = source_document.get("sha256") if isinstance(source_document, Mapping) else None
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise ValueError(
                    "direct_pdf_render source_reference requires a valid source_document.sha256"
                )
            if digest.lower() != source_document_sha256.lower():
                raise ValueError(
                    "direct_pdf_render source_reference.sha256 does not match source_document.sha256"
                )
            reference["source_page"] = source_page
            reference["source_reference"] = deepcopy(dict(source_reference))
    if isinstance(image_path, str) and image_path:
        reference["image"] = image_path
    return reference


def build_movement_boundary_evidence(
    numbering_base: Mapping[str, Any],
    *,
    source_document: Mapping[str, Any],
    producer_source_commit: str,
    manifest_pages: Sequence[Mapping[str, Any]] | None = None,
    numbering_artifact: str | None = None,
    indent_ratio: float = DEFAULT_INDENT_RATIO,
    gap_ratio: float = DEFAULT_GAP_RATIO,
) -> dict[str, Any]:
    """Build review-only evidence from normalized system layout.

    ``page`` is always the zero-based position in ``numbering_base["pages"]``.
    Optional manifest references retain the source page identity separately.
    The first non-empty input system is recorded as ``no_boundary`` because a
    reset before the initial numbering state is unnecessary.
    """
    pages = numbering_base.get("pages")
    if not isinstance(pages, list):
        raise ValueError("numbering_base must contain a pages list")
    if manifest_pages is not None and len(manifest_pages) != len(pages):
        raise ValueError("manifest page count must match numbering_base page count")
    if not isinstance(source_document, Mapping):
        raise ValueError("source_document must be an object")
    source_sha256 = source_document.get("sha256")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha256):
        raise ValueError("source_document.sha256 must be a 64-character hexadecimal digest")
    if not isinstance(producer_source_commit, str) or not producer_source_commit.strip():
        raise ValueError("producer_source_commit must be non-empty")
    if indent_ratio < 0 or gap_ratio <= 0:
        raise ValueError("movement candidate ratios must be positive")

    first_system = next(
        (
            (page_index, 0)
            for page_index, page in enumerate(pages)
            if isinstance(page, Mapping) and page.get("systems")
        ),
        None,
    )
    records = []
    for page_index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise ValueError("numbering_base pages must be objects")
        width = page.get("width")
        height = page.get("height")
        systems = page.get("systems")
        if not isinstance(width, (int, float)) or width <= 0:
            raise ValueError("numbering_base page width must be positive")
        if not isinstance(height, (int, float)) or height <= 0:
            raise ValueError("numbering_base page height must be positive")
        if not isinstance(systems, list):
            raise ValueError("numbering_base page systems must be a list")
        if not systems:
            continue
        boxes = [_system_box(system) for system in systems]
        left_median = median(box[0] for box in boxes)
        gaps = [boxes[index][1] - boxes[index - 1][3] for index in range(1, len(boxes))]
        gap_median = median(gaps) if gaps else None
        page_reference = _page_reference(
            manifest_pages[page_index] if manifest_pages is not None else None,
            source_document_sha256=source_sha256,
        )
        for system_index, box in enumerate(boxes):
            indent_value = (box[0] - left_median) / width
            preceding_gap = gaps[system_index - 1] if system_index else None
            preceding_gap_ratio = (
                preceding_gap / gap_median
                if preceding_gap is not None and gap_median not in (None, 0)
                else None
            )
            signals = []
            if indent_value >= indent_ratio:
                signals.append("relative_indent")
            if preceding_gap_ratio is not None and preceding_gap_ratio >= gap_ratio:
                signals.append("whitespace_outlier")
            is_initial = first_system == (page_index, system_index)
            if not signals and not is_initial:
                continue
            raw = {
                "system_bbox": [round(value, 3) for value in box],
                "geometry_representation": "all_staff_union",
                "page_width": width,
                "page_height": height,
                "left_median_px": round(left_median, 3),
                "indent_page_ratio": round(indent_value, 6),
                "preceding_gap_px": preceding_gap,
                "preceding_gap_to_page_median": (
                    round(preceding_gap_ratio, 6) if preceding_gap_ratio is not None else None
                ),
                "matched_rules": signals,
            }
            evidence_signals = []
            if signals:
                evidence_signals.append(
                    {
                        "kind": "system_layout",
                        "artifact": numbering_artifact,
                        "raw": raw,
                    }
                )
            if is_initial:
                evidence_signals.append(
                    {
                        "kind": "initial_input_system",
                        "artifact": numbering_artifact,
                        "raw": {"reset_required": False},
                    }
                )
            record = {
                "id": f"page:{page_index}:system:{system_index}",
                "page": page_index,
                "system": system_index,
                "state": "no_boundary" if is_initial else "ambiguous_review_required",
                "signals": evidence_signals,
                "references": deepcopy(page_reference),
                "provenance": {"review": None},
            }
            records.append(record)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "source_document": deepcopy(dict(source_document)),
        "coordinate_system": {
            "page": "zero-based ordered pipeline input page",
            "system": "zero-based system in numbering_base page",
            "source_page": "optional zero-based physical PDF page retained in references",
        },
        "producer": {
            "name": PRODUCER_NAME,
            "version": PRODUCER_VERSION,
            "source_commit": producer_source_commit,
            "parameters": {
                "relative_indent_min_page_ratio": indent_ratio,
                "preceding_gap_min_page_median_ratio": gap_ratio,
                "initial_input_system": "no_boundary",
            },
        },
        "candidates": records,
    }
