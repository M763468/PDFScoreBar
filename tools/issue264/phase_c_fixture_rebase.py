"""Evaluation-only rebase of historical MMR fixtures onto current numbering geometry.

Historical Issue #94/#221 fixtures identify an MMR by ``[page, system, measure]``.
Those indices are not stable when Phase A grouping changes.  For current Phase C
acceptance, use the historical numbering payload only as GT geometry: locate the
historical measure bbox named by the fixture, then map that bbox to the current
Phase A measure occupying the same page region.

This module is evaluation tooling only.  Historical numbering artifacts must never
become production pipeline inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MeasureRef:
    system: int
    measure: int
    bbox: tuple[float, float, float, float]


def _normalise_bbox(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"Measure bbox must be a four-element list, got {value!r}")
    x1, y1, x2, y2 = (float(v) for v in value)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid measure bbox: {value!r}")
    return x1, y1, x2, y2


def _single_page(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Numbering payload must contain exactly one page")
    return pages[0]


def iter_measures(payload: Mapping[str, Any]) -> list[MeasureRef]:
    page = _single_page(payload)
    systems = page.get("systems")
    if not isinstance(systems, list):
        raise ValueError("Numbering page lacks systems")
    refs: list[MeasureRef] = []
    for system_index, system in enumerate(systems):
        if not isinstance(system, Mapping):
            raise ValueError(f"Malformed system at index {system_index}")
        measures = system.get("measures")
        if not isinstance(measures, list):
            raise ValueError(f"System {system_index} lacks measures")
        for measure_index, measure in enumerate(measures):
            if not isinstance(measure, Mapping):
                raise ValueError(
                    f"Malformed measure at system={system_index} measure={measure_index}"
                )
            refs.append(
                MeasureRef(
                    system=system_index,
                    measure=measure_index,
                    bbox=_normalise_bbox(measure.get("bbox")),
                )
            )
    return refs


def measure_for_index(payload: Mapping[str, Any], *, system: int, measure: int) -> MeasureRef:
    for ref in iter_measures(payload):
        if ref.system == system and ref.measure == measure:
            return ref
    raise IndexError(f"Historical fixture index is absent: system={system} measure={measure}")


def _center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _contains(bbox: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    x1, y1, x2, y2 = bbox
    x, y = point
    return x1 <= x <= x2 and y1 <= y <= y2


def _intersection_area(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    width = max(0.0, min(lx2, rx2) - max(lx1, rx1))
    height = max(0.0, min(ly2, ry2) - max(ly1, ry1))
    return width * height


def _area(bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    return (x2 - x1) * (y2 - y1)


def _overlap_score(
    historical: tuple[float, float, float, float], current: tuple[float, float, float, float]
) -> float:
    intersection = _intersection_area(historical, current)
    if intersection <= 0:
        return 0.0
    return intersection / min(_area(historical), _area(current))


def map_measure_bbox(
    historical: MeasureRef,
    current_payload: Mapping[str, Any],
    *,
    minimum_overlap: float = 0.50,
) -> tuple[MeasureRef, dict[str, Any]]:
    """Map one historical measure to the current physical measure at the same location.

    Prefer the current measure containing the historical bbox center.  If geometry
    shifts move that center just outside the new bbox, fall back to strongest 2-D
    overlap.  Ambiguous or weak mappings fail rather than silently changing GT.
    """

    candidates = iter_measures(current_payload)
    center = _center(historical.bbox)
    containing = [ref for ref in candidates if _contains(ref.bbox, center)]

    if containing:
        ranked = sorted(
            ((_overlap_score(historical.bbox, ref.bbox), ref) for ref in containing),
            key=lambda item: item[0],
            reverse=True,
        )
        method = "historical_center_in_current_bbox"
    else:
        ranked = sorted(
            ((_overlap_score(historical.bbox, ref.bbox), ref) for ref in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        method = "maximum_bbox_overlap"

    if not ranked or ranked[0][0] < minimum_overlap:
        best = ranked[0][0] if ranked else 0.0
        raise ValueError(
            "Could not spatially rebase historical measure "
            f"system={historical.system} measure={historical.measure}; best overlap={best:.3f}"
        )

    best_score, best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if second_score >= minimum_overlap and abs(best_score - second_score) < 0.05:
        raise ValueError(
            "Ambiguous spatial rebase for historical measure "
            f"system={historical.system} measure={historical.measure}; "
            f"best={best_score:.3f} second={second_score:.3f}"
        )

    return best, {
        "method": method,
        "overlap_score": best_score,
        "historical_bbox": list(historical.bbox),
        "current_bbox": list(best.bbox),
    }


def normalise_overrides(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("measure_overrides", "overrides"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    return []


def rebase_expected_overrides(
    expected_payload: Any,
    historical_numbering: Mapping[str, Any],
    current_numbering: Mapping[str, Any],
    *,
    global_page_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rebased: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    seen_current_keys: set[tuple[int, int, int]] = set()

    for item in normalise_overrides(expected_payload):
        old_system = int(item["system"])
        old_measure = int(item["measure"])
        historical_ref = measure_for_index(
            historical_numbering,
            system=old_system,
            measure=old_measure,
        )
        current_ref, detail = map_measure_bbox(historical_ref, current_numbering)
        current_key = (global_page_index, current_ref.system, current_ref.measure)
        if current_key in seen_current_keys:
            raise ValueError(f"Multiple historical fixtures map to current key {current_key}")
        seen_current_keys.add(current_key)

        mapped = dict(item)
        mapped["page"] = global_page_index
        mapped["system"] = current_ref.system
        mapped["measure"] = current_ref.measure
        rebased.append(mapped)
        mappings.append(
            {
                "historical_key": [global_page_index, old_system, old_measure],
                "current_key": list(current_key),
                "changed": [old_system, old_measure]
                != [current_ref.system, current_ref.measure],
                **detail,
            }
        )

    return {"overrides": rebased}, mappings


def mapping_method_counts(mappings: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for mapping in mappings:
        method = str(mapping.get("method", "unknown"))
        counts[method] = counts.get(method, 0) + 1
    return counts
