"""Build MMR-only views by reusing current-x4 HOMR support artifacts.

The Phase-A numbering payload remains authoritative for topology, numbering and
horizontal geometry.  This module only supplies vertical staff geometry to MMR.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from src.measure_numbering.pipeline import StaffExtractor
from src.pipeline.utils.io import load_json, write_json

SCHEMA_VERSION = "pipeline.mmr_support_reuse.v1"


def _bbox(value: Mapping[str, Any]) -> list[int]:
    bbox = value.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("MMR support requires four-value staff bounding boxes")
    return [int(item) for item in bbox]


def _overlap_ratio(a: list[int], b: list[int], axis: int) -> float:
    start, end = axis, axis + 2
    overlap = max(0, min(a[end], b[end]) - max(a[start], b[start]))
    return overlap / max(1, min(a[end] - a[start], b[end] - b[start]))


def _candidate_record(index: int, base: list[int], candidate: list[int]) -> dict[str, Any]:
    base_height = max(1, base[3] - base[1])
    candidate_height = max(1, candidate[3] - candidate[1])
    center_distance = abs((base[1] + base[3]) / 2 - (candidate[1] + candidate[3]) / 2)
    return {
        "index": index,
        "bbox": candidate,
        "vertical_overlap": _overlap_ratio(base, candidate, 1),
        "horizontal_overlap": _overlap_ratio(base, candidate, 0),
        "center_distance_ratio": center_distance / max(base_height, candidate_height),
    }


def _matches(record: Mapping[str, Any]) -> bool:
    """Use only scale-free geometry; no page-specific or pixel thresholds."""

    return bool(record["vertical_overlap"] > 0 and record["center_distance_ratio"] <= 0.5)


def _raw_mapped_bbox(base: list[int], candidates: list[dict[str, Any]]) -> tuple[list[int], str]:
    if not candidates:
        return base, "phase_a_fallback"
    if len(candidates) == 1:
        return list(candidates[0]["bbox"]), "single_current_staff"
    return [
        min(item["bbox"][0] for item in candidates),
        min(item["bbox"][1] for item in candidates),
        max(item["bbox"][2] for item in candidates),
        max(item["bbox"][3] for item in candidates),
    ], "union_current_staff"


def _is_implicit_start(measure: Mapping[str, Any], base_sys_x1: int) -> bool:
    """Recognise only the already-present Phase-A system-start geometry."""

    return _bbox(measure)[0] == base_sys_x1 + 1


def build_mmr_support_data(
    numbering_base: Mapping[str, Any], current_homr_staff_mask: Path
) -> dict[str, Any]:
    """Return immutable Phase-A views with current-x4 staff y coordinates."""

    pages = numbering_base.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("MMR support expects exactly one Phase-A page payload")
    page = pages[0]
    width, height = int(page["width"]), int(page["height"])
    current_staves = [
        [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]
        for staff in StaffExtractor().extract(current_homr_staff_mask, (width, height))
    ]
    primary = deepcopy(numbering_base)
    alternate = deepcopy(numbering_base)
    fallback = deepcopy(numbering_base)
    mappings: list[dict[str, Any]] = []
    mapped_count = union_count = fallback_count = 0

    for sys_idx, system in enumerate(page.get("systems", [])):
        base_system = system
        primary_system = primary["pages"][0]["systems"][sys_idx]
        alternate_system = alternate["pages"][0]["systems"][sys_idx]
        effective_staves: list[list[int]] = []
        raw_mapped_staves: list[list[int]] = []
        for staff_idx, staff in enumerate(base_system.get("staves", [])):
            base_bbox = _bbox(staff)
            candidates = [
                _candidate_record(index, base_bbox, candidate)
                for index, candidate in enumerate(current_staves)
            ]
            candidates = [item for item in candidates if _matches(item)]
            raw_mapped, mode = _raw_mapped_bbox(base_bbox, candidates)
            effective = [base_bbox[0], raw_mapped[1], base_bbox[2], raw_mapped[3]]
            if mode == "phase_a_fallback":
                fallback_count += 1
            else:
                mapped_count += 1
                if mode == "union_current_staff":
                    union_count += 1
            primary_system["staves"][staff_idx]["bbox"] = effective
            alternate_system["staves"][staff_idx]["bbox"] = effective
            effective_staves.append(effective)
            raw_mapped_staves.append(raw_mapped)
            mappings.append(
                {
                    "system": sys_idx,
                    "staff": staff_idx,
                    "base_bbox": base_bbox,
                    "raw_mapped_bbox": raw_mapped,
                    "effective_bbox": effective,
                    "mode": mode,
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                }
            )

        if not effective_staves:
            continue
        envelope_y1 = min(item[1] for item in effective_staves)
        envelope_y2 = max(item[3] for item in effective_staves)
        base_sys_x1 = min(_bbox(staff)[0] for staff in base_system.get("staves", []))
        mapped_sys_x1 = min(item[0] for item in raw_mapped_staves)
        primary_system["measures"] = deepcopy(base_system.get("measures", []))
        alternate_system["measures"] = deepcopy(base_system.get("measures", []))
        for measure_idx, measure in enumerate(base_system.get("measures", [])):
            base_measure_bbox = _bbox(measure)
            primary_bbox = [base_measure_bbox[0], envelope_y1, base_measure_bbox[2], envelope_y2]
            primary_system["measures"][measure_idx]["bbox"] = primary_bbox
            alternate_bbox = list(primary_bbox)
            if measure_idx == 0 and _is_implicit_start(measure, base_sys_x1):
                alternate_bbox[0] = mapped_sys_x1 + 1
            alternate_system["measures"][measure_idx]["bbox"] = alternate_bbox

    staff_slot_count = len(mappings)
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": {
            "schema_version": SCHEMA_VERSION,
            "source": "current_x4_support",
            "current_homr_staff_mask": str(current_homr_staff_mask),
            "coordinate_space": "source_page",
            "topology_source": "phase_a_numbering_base",
            "normal_x_source": "phase_a_final_hybrid_barlines",
            "primary_y_source": "current_x4_homr",
            "original_image_homr": False,
            "second_numbering_rebuild": False,
            "staff_slot_count": staff_slot_count,
            "mapped_count": mapped_count,
            "fallback_count": fallback_count,
            "union_count": union_count,
            "mappings": mappings,
        },
        "views": {
            "primary": primary,
            "implicit_start_alternate": alternate,
            "fallback": fallback,
        },
    }


def build_mmr_support(
    *, numbering_base_path: Path, current_homr_staff_mask: Path, output_path: Path
) -> dict[str, Any]:
    """Build and persist one page's MMR support sidecar."""

    if not current_homr_staff_mask.is_file():
        raise FileNotFoundError(f"Missing current-x4 HOMR staff mask: {current_homr_staff_mask}")
    support = build_mmr_support_data(load_json(numbering_base_path), current_homr_staff_mask)
    write_json(output_path, support)
    return support
