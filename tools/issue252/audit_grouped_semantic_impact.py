#!/usr/bin/env python3
"""Audit one detector box-instance difference through connector-grouped numbering."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Mapping, Sequence

Box = tuple[int, int, int, int]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bbox(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    try:
        return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _vertical_overlap(left: Box, right: Box) -> int:
    return max(0, min(left[3], right[3]) - max(left[1], right[1]))


def _horizontal_overlap(left: Box, right: Box) -> int:
    return max(0, min(left[2], right[2]) - max(left[0], right[0]))


def _center_x(box: Box) -> float:
    return (box[0] + box[2]) / 2.0


def _page_payload(payload: Any, page_number: int) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Numbering payload must be a JSON object")
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Numbering payload must contain pages[]")
    for page in pages:
        if isinstance(page, Mapping) and int(page.get("page_number", -1)) == page_number:
            return page
    raise ValueError(f"Could not resolve page_number={page_number}")


def _component_boxes(page: Mapping[str, Any]) -> list[Box]:
    boxes = []
    for system in page.get("systems", []):
        if not isinstance(system, Mapping):
            continue
        for component in system.get("staves", []):
            if isinstance(component, Mapping) and (box := _bbox(component.get("bbox"))) is not None:
                boxes.append(box)
    return sorted(boxes, key=lambda box: (box[1], box[0], box[3], box[2]))


def _component_index(box: Box, ordered_boxes: Sequence[Box]) -> int:
    matches = [index for index, item in enumerate(ordered_boxes) if item == box]
    if len(matches) != 1:
        raise ValueError(f"Expected one serialized component matching {box}, found {len(matches)}")
    return matches[0]


def _measure_signature(measure: Mapping[str, Any]) -> dict[str, Any]:
    box = _bbox(measure.get("bbox"))
    return {
        "number": measure.get("number"),
        "bbox": list(box) if box is not None else None,
    }


def _system_signature(
    system: Mapping[str, Any],
    index: int,
    ordered_components: Sequence[Box],
) -> dict[str, Any]:
    component_boxes = [
        box
        for item in system.get("staves", [])
        if isinstance(item, Mapping) and (box := _bbox(item.get("bbox"))) is not None
    ]
    measures = [
        _measure_signature(item) for item in system.get("measures", []) if isinstance(item, Mapping)
    ]
    boundaries = sorted(
        {
            x
            for measure in measures
            if isinstance(measure.get("bbox"), list)
            for x in (measure["bbox"][0], measure["bbox"][2])
        }
    )
    return {
        "index": index,
        "component_count": len(component_boxes),
        "components": [list(box) for box in component_boxes],
        "component_indices": [_component_index(box, ordered_components) for box in component_boxes],
        "measure_count": len(measures),
        "row_start": measures[0].get("number") if measures else None,
        "measure_boundaries_x": boundaries,
        "measures": measures,
    }


def _page_summary(page: Mapping[str, Any], systems: list[dict[str, Any]]) -> dict[str, Any]:
    measure_numbers = [
        measure.get("number")
        for system in systems
        for measure in system["measures"]
        if isinstance(measure.get("number"), int)
    ]
    return {
        "system_count": len(systems),
        "empty_system_count": len(page.get("empty_systems", [])),
        "component_count": sum(system["component_count"] for system in systems),
        "measure_count": sum(system["measure_count"] for system in systems),
        "last_measure_number": max(measure_numbers, default=None),
        "systems": systems,
    }


def _geometry_signature(system: Mapping[str, Any] | None) -> list[Any] | None:
    if system is None:
        return None
    return [measure.get("bbox") for measure in system.get("measures", [])]


def _numbering_signature(system: Mapping[str, Any] | None) -> list[Any] | None:
    if system is None:
        return None
    return [(measure.get("number"), measure.get("bbox")) for measure in system.get("measures", [])]


def _compare_page_summaries(
    default: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    default_systems = list(default.get("systems", []))
    candidate_systems = list(candidate.get("systems", []))
    system_count = max(len(default_systems), len(candidate_systems))
    per_system = []
    changed_geometry: list[int] = []
    changed_numbering: list[int] = []
    changed_component_grouping: list[int] = []

    for index in range(system_count):
        default_system = default_systems[index] if index < len(default_systems) else None
        candidate_system = candidate_systems[index] if index < len(candidate_systems) else None
        default_measure_count = (
            int(default_system.get("measure_count", 0)) if default_system is not None else 0
        )
        candidate_measure_count = (
            int(candidate_system.get("measure_count", 0)) if candidate_system is not None else 0
        )
        geometry_equal = _geometry_signature(default_system) == _geometry_signature(candidate_system)
        numbering_equal = _numbering_signature(default_system) == _numbering_signature(
            candidate_system
        )
        component_grouping_equal = (
            default_system.get("components") if default_system is not None else None
        ) == (candidate_system.get("components") if candidate_system is not None else None)

        if not geometry_equal:
            changed_geometry.append(index)
        if not numbering_equal:
            changed_numbering.append(index)
        if not component_grouping_equal:
            changed_component_grouping.append(index)

        per_system.append(
            {
                "system_index": index,
                "default_measure_count": default_measure_count,
                "candidate_measure_count": candidate_measure_count,
                "measure_count_delta": candidate_measure_count - default_measure_count,
                "geometry_equal": geometry_equal,
                "numbering_equal": numbering_equal,
                "component_grouping_equal": component_grouping_equal,
            }
        )

    default_measure_count = int(default.get("measure_count", 0))
    candidate_measure_count = int(candidate.get("measure_count", 0))
    measure_count_delta = candidate_measure_count - default_measure_count
    broad_geometry_change = (
        len(changed_geometry) > 1
        or abs(measure_count_delta) > 1
        or len(default_systems) != len(candidate_systems)
    )
    return {
        "default_measure_count": default_measure_count,
        "candidate_measure_count": candidate_measure_count,
        "measure_count_delta": measure_count_delta,
        "default_last_measure_number": default.get("last_measure_number"),
        "candidate_last_measure_number": candidate.get("last_measure_number"),
        "system_count_equal": len(default_systems) == len(candidate_systems),
        "component_count_equal": default.get("component_count") == candidate.get("component_count"),
        "changed_geometry_system_indices": changed_geometry,
        "changed_geometry_system_count": len(changed_geometry),
        "changed_numbering_system_indices": changed_numbering,
        "changed_numbering_system_count": len(changed_numbering),
        "changed_component_grouping_system_indices": changed_component_grouping,
        "changed_component_grouping_system_count": len(changed_component_grouping),
        "broad_geometry_change": broad_geometry_change,
        "geometry_equal": not changed_geometry,
        "numbering_equal": not changed_numbering,
        "component_grouping_equal": not changed_component_grouping,
        "per_system": per_system,
    }


def _connector_pairs(payload: Any) -> dict[tuple[int, int], dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Connector evidence must be a JSON object")
    pairs = {}
    for item in payload.get("staff_pairs", []):
        if not isinstance(item, Mapping):
            continue
        pair = item.get("staff_pair")
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes)) or len(pair) != 2:
            continue
        key = (int(pair[0]), int(pair[1]))
        pairs[key] = dict(item)
    return pairs


def _connector_component(
    start: int,
    allowed: set[int],
    pairs: Mapping[tuple[int, int], Mapping[str, Any]],
) -> set[int]:
    graph: dict[int, set[int]] = defaultdict(set)
    for (left, right), evidence in pairs.items():
        if left not in allowed or right not in allowed:
            continue
        if evidence.get("left_connector_present") is not True:
            continue
        graph[left].add(right)
        graph[right].add(left)

    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in graph[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited


def _target_component_memberships(
    systems: Sequence[Mapping[str, Any]],
    target: Box,
) -> list[dict[str, Any]]:
    target_height = max(1, target[3] - target[1])
    memberships = []
    for system in systems:
        for local_index, component_box_raw in enumerate(system.get("components", [])):
            component_box = _bbox(component_box_raw)
            if component_box is None:
                continue
            vertical_overlap = _vertical_overlap(target, component_box)
            target_x_inside_component = (
                component_box[0] - 12 <= _center_x(target) <= component_box[2] + 12
            )
            if vertical_overlap <= 0 or not target_x_inside_component:
                continue
            memberships.append(
                {
                    "system_index": int(system["index"]),
                    "component_local_index": local_index,
                    "component_index": int(system["component_indices"][local_index]),
                    "component_bbox": list(component_box),
                    "vertical_overlap_px": vertical_overlap,
                    "target_vertical_overlap_ratio": vertical_overlap / target_height,
                    "horizontal_overlap_px": _horizontal_overlap(target, component_box),
                }
            )
    memberships.sort(
        key=lambda item: (
            -item["target_vertical_overlap_ratio"],
            -item["vertical_overlap_px"],
            item["system_index"],
            item["component_local_index"],
        )
    )
    return memberships


def _boundary_matches(
    system: Mapping[str, Any],
    target: Box,
    tolerance: float,
) -> list[dict[str, Any]]:
    target_x = _center_x(target)
    matches = []
    for boundary_x in system.get("measure_boundaries_x", []):
        distance = abs(float(boundary_x) - target_x)
        if distance <= tolerance:
            matches.append({"x": boundary_x, "distance": distance})
    return sorted(matches, key=lambda item: (item["distance"], item["x"]))


def _route_evidence(
    numbering_payload: Any,
    connector_payload: Any,
    *,
    page_number: int,
    target: Box,
    x_tolerance: float,
) -> dict[str, Any]:
    page = _page_payload(numbering_payload, page_number)
    ordered_components = _component_boxes(page)
    systems = [
        _system_signature(system, index, ordered_components)
        for index, system in enumerate(page.get("systems", []))
        if isinstance(system, Mapping)
    ]
    page_summary = _page_summary(page, systems)
    memberships = _target_component_memberships(systems, target)
    pairs = _connector_pairs(connector_payload)
    if not memberships:
        return {
            "status": "target_component_unresolved",
            "page_number": page_number,
            "memberships": [],
            "owning_system": None,
            "target_boundary_matches": [],
            "page_summary": page_summary,
        }

    selected = memberships[0]
    owning_system = systems[selected["system_index"]]
    allowed = set(owning_system["component_indices"])
    connected = _connector_component(selected["component_index"], allowed, pairs)
    positive_pairs = [
        {
            "pair": [left, right],
            "left_connector_present": True,
        }
        for (left, right), evidence in sorted(pairs.items())
        if left in allowed and right in allowed and evidence.get("left_connector_present") is True
    ]
    return {
        "status": "resolved",
        "page_number": page_number,
        "memberships": memberships,
        "selected_membership": selected,
        "owning_system": owning_system,
        "connector_supported_component_indices": sorted(connected),
        "connector_supported_grouping": len(connected) > 1,
        "positive_connector_pairs_in_system": positive_pairs,
        "target_boundary_matches": _boundary_matches(owning_system, target, x_tolerance),
        "page_summary": page_summary,
    }


def compare_grouped_final_numbering(
    default: dict[str, Any],
    candidate: dict[str, Any],
    *,
    connector_evidence_equal: bool | None = None,
) -> dict[str, Any]:
    page_comparison = _compare_page_summaries(default["page_summary"], candidate["page_summary"])
    if default["status"] != "resolved" or candidate["status"] != "resolved":
        classification = "target_component_unresolved"
        semantic_equal = False
    elif connector_evidence_equal is False:
        classification = "connector_evidence_changed"
        semantic_equal = False
    elif page_comparison["broad_geometry_change"]:
        classification = "candidate_page_wide_numbering_drift"
        semantic_equal = False
    elif not default["connector_supported_grouping"]:
        classification = "default_grouping_not_connector_supported"
        semantic_equal = False
    elif not candidate["connector_supported_grouping"]:
        classification = "candidate_grouping_not_connector_supported"
        semantic_equal = False
    elif not default["target_boundary_matches"]:
        semantic_equal = False
        classification = (
            "target_boundary_recovered_with_local_numbering_change"
            if candidate["target_boundary_matches"]
            else "default_grouped_system_boundary_missing"
        )
    else:
        semantic_equal = (
            default["owning_system"] == candidate["owning_system"]
            and page_comparison["numbering_equal"]
        )
        classification = (
            "redundant_connector_grouped_component_fn"
            if semantic_equal and candidate["target_boundary_matches"]
            else "downstream_grouped_numbering_difference"
        )

    return {
        "semantic_equal": semantic_equal,
        "classification": classification,
        "connector_evidence_equal": connector_evidence_equal,
        "page_comparison": page_comparison,
        "default": default,
        "candidate": candidate,
    }


def normalize_isolated_mmr_overrides(
    overrides_payload: Any,
    *,
    serialized_page_number: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map MMR's serialized page key to index 0 for an isolated one-page Score."""
    if not isinstance(overrides_payload, Mapping):
        raise ValueError("MMR overrides payload must be a JSON object")
    raw = overrides_payload.get("measure_overrides")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError("measure_overrides must be a list")

    expected_page_key = serialized_page_number - 1
    normalized = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Each MMR override must be an object")
        source_page = item.get("page")
        if source_page != expected_page_key:
            raise ValueError(
                "Unexpected MMR page key for isolated run: "
                f"expected={expected_page_key} actual={source_page}"
            )
        converted = dict(item)
        converted["source_page"] = source_page
        converted["page"] = 0
        normalized.append(converted)
    return [dict(item) for item in raw], normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default-numbering", type=Path, required=True)
    parser.add_argument("--candidate-numbering", type=Path, required=True)
    parser.add_argument("--default-connector-evidence", type=Path, required=True)
    parser.add_argument("--candidate-connector-evidence", type=Path, required=True)
    parser.add_argument("--page-number", type=int, required=True)
    parser.add_argument("--target-bbox", type=int, nargs=4, required=True)
    parser.add_argument("--x-tolerance", type=float, default=12.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue252_grouped_final_numbering_audit.json"),
    )
    args = parser.parse_args()
    target = tuple(args.target_bbox)  # type: ignore[assignment]

    default_connector = _load(args.default_connector_evidence)
    candidate_connector = _load(args.candidate_connector_evidence)
    default = _route_evidence(
        _load(args.default_numbering),
        default_connector,
        page_number=args.page_number,
        target=target,
        x_tolerance=args.x_tolerance,
    )
    candidate = _route_evidence(
        _load(args.candidate_numbering),
        candidate_connector,
        page_number=args.page_number,
        target=target,
        x_tolerance=args.x_tolerance,
    )
    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=default_connector == candidate_connector,
    )
    result.update(
        {
            "schema_version": "issue252.grouped_final_numbering_audit.v3",
            "status": "completed",
            "page_number": args.page_number,
            "target_bbox": list(target),
        }
    )
    _write(args.output, result)
    print(
        json.dumps(
            {
                "status": "completed",
                "classification": result["classification"],
                "output": str(args.output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
