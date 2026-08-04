"""Structured rescue for probe candidates rejected only by paper overlap."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

Box = tuple[int, int, int, int]


def _box(value: Sequence[Any]) -> Box:
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _center_x(box: Box) -> float:
    return (box[0] + box[2]) / 2.0


def _center_y(box: Box) -> float:
    return (box[1] + box[3]) / 2.0


def _width(box: Box) -> int:
    return abs(box[2] - box[0])


def _height(box: Box) -> int:
    return abs(box[3] - box[1])


def _band(box: Box) -> tuple[int, int]:
    return min(box[1], box[3]), max(box[1], box[3])


def _vertical_overlap_ratio(first: Box, second: Box) -> float:
    first_y1, first_y2 = _band(first)
    second_y1, second_y2 = _band(second)
    intersection = max(0, min(first_y2, second_y2) - max(first_y1, second_y1))
    return float(intersection) / float(max(1, min(_height(first), _height(second))))


def _duplicates_narrow_existing(
    candidate: Box,
    existing_boxes: Sequence[Box],
    *,
    x_tolerance: int,
    wide_seed_width_ratio: float,
) -> bool:
    """Return whether a candidate duplicates an already narrow same-band seed."""
    candidate_width = max(1, _width(candidate))
    wide_seed_min_width = max(12.0, wide_seed_width_ratio * candidate_width)
    for existing in existing_boxes:
        if abs(_center_x(existing) - _center_x(candidate)) > x_tolerance:
            continue
        if _vertical_overlap_ratio(candidate, existing) < 0.5:
            continue
        if _width(existing) < wide_seed_min_width:
            return True
    return False


def rescue_low_paper_candidates(
    *,
    dropped: Sequence[Mapping[str, Any]],
    existing_boxes: Sequence[Box],
    median_height: float,
    min_ink_ratio: float = 0.9,
    max_height_median_ratio: float = 1.4,
    gap_ratio: float = 1.5,
    gap_margin_ratio: float = 0.1,
    gap_nms_ratio: float = 0.5,
    x_tolerance_height_ratio: float = 0.04,
    min_x_tolerance: int = 4,
    wide_seed_width_ratio: float = 3.0,
    cross_band_max_distance_height_ratio: float = 4.0,
) -> tuple[list[Box], list[dict[str, Any]], list[dict[str, Any]]]:
    """Rescue only strongly supported verticals rejected solely as non-paper.

    A narrow dark line naturally has little bright-paper overlap inside its own
    bounding box. It is eligible only when no other heuristic rejected it, it
    does not duplicate an already narrow same-band seed, and one of three
    source-general geometry checks supports it:

    * it splits an abnormally large gap between existing barlines;
    * it aligns with a candidate or existing barline in another staff row;
    * it is a narrow refinement of a much wider existing seed.
    """
    remaining = [dict(item) for item in dropped]
    if median_height <= 0:
        return [], remaining, []

    eligible: list[dict[str, Any]] = []
    for item in remaining:
        reasons = item.get("reasons")
        bbox = item.get("bbox")
        if reasons != ["low_paper_overlap"] or not isinstance(bbox, Sequence):
            continue
        normalized = _box(bbox)
        if float(item.get("ink_ratio", 0.0)) < min_ink_ratio:
            continue
        if _height(normalized) > median_height * max_height_median_ratio:
            continue
        eligible.append({**item, "bbox": normalized})

    if not eligible:
        return [], remaining, []

    normalized_existing = [_box(box) for box in existing_boxes]
    x_tolerance = max(
        int(min_x_tolerance),
        int(round(median_height * x_tolerance_height_ratio)),
    )
    eligible = [
        item
        for item in eligible
        if not _duplicates_narrow_existing(
            _box(item["bbox"]),
            normalized_existing,
            x_tolerance=x_tolerance,
            wide_seed_width_ratio=wide_seed_width_ratio,
        )
    ]
    if not eligible:
        return [], remaining, []

    candidate_bands = sorted({_band(item["bbox"]) for item in eligible})
    existing_x_by_band: dict[tuple[int, int], list[float]] = {}
    all_gaps: list[float] = []
    for band in candidate_bands:
        xs = sorted(
            {_center_x(box) for box in normalized_existing if band[0] <= _center_y(box) <= band[1]}
        )
        existing_x_by_band[band] = xs
        all_gaps.extend(right - left for left, right in zip(xs, xs[1:]) if right > left)
    median_gap = float(median(all_gaps)) if all_gaps else 0.0

    selected: dict[Box, dict[str, Any]] = {}
    supports: dict[Box, set[str]] = defaultdict(set)

    def select(item: Mapping[str, Any], support: str) -> None:
        box = _box(item["bbox"])
        selected.setdefault(box, dict(item))
        supports[box].add(support)

    if median_gap > 0:
        gap_groups: dict[tuple[tuple[int, int], float, float], list[dict[str, Any]]] = defaultdict(
            list
        )
        for item in eligible:
            box = _box(item["bbox"])
            x_center = _center_x(box)
            xs = existing_x_by_band[_band(box)]
            left = max((value for value in xs if value < x_center), default=None)
            right = min((value for value in xs if value > x_center), default=None)
            if left is None or right is None:
                continue
            gap_width = right - left
            if gap_width < median_gap * gap_ratio:
                continue
            if min(x_center - left, right - x_center) < gap_width * gap_margin_ratio:
                continue
            gap_groups[(_band(box), left, right)].append(item)

        for candidates in gap_groups.values():
            kept: list[dict[str, Any]] = []
            ordered = sorted(
                candidates,
                key=lambda item: (
                    -float(item.get("ink_ratio", 0.0)),
                    _width(_box(item["bbox"])),
                    _box(item["bbox"]),
                ),
            )
            for item in ordered:
                x_center = _center_x(_box(item["bbox"]))
                if any(
                    abs(x_center - _center_x(_box(previous["bbox"]))) < median_gap * gap_nms_ratio
                    for previous in kept
                ):
                    continue
                kept.append(item)
                select(item, "large_gap")

    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(eligible, key=lambda value: _center_x(_box(value["bbox"]))):
        x_center = _center_x(_box(item["bbox"]))
        if clusters:
            cluster_center = float(median(_center_x(_box(value["bbox"])) for value in clusters[-1]))
            if abs(x_center - cluster_center) <= x_tolerance:
                clusters[-1].append(item)
                continue
        clusters.append([item])

    for cluster in clusters:
        best_by_band: dict[tuple[int, int], dict[str, Any]] = {}
        for item in cluster:
            band = _band(_box(item["bbox"]))
            previous = best_by_band.get(band)
            if previous is None or (
                float(item.get("ink_ratio", 0.0)),
                -_width(_box(item["bbox"])),
            ) > (
                float(previous.get("ink_ratio", 0.0)),
                -_width(_box(previous["bbox"])),
            ):
                best_by_band[band] = item

        non_overlapping: list[dict[str, Any]] = []
        for item in sorted(best_by_band.values(), key=lambda value: _band(_box(value["bbox"]))):
            box = _box(item["bbox"])
            if all(
                _vertical_overlap_ratio(box, _box(previous["bbox"])) < 0.2
                for previous in non_overlapping
            ):
                non_overlapping.append(item)
        if len(non_overlapping) >= 2:
            for item in non_overlapping:
                select(item, "aligned_candidate")

    for item in eligible:
        box = _box(item["bbox"])
        for existing in normalized_existing:
            if abs(_center_x(existing) - _center_x(box)) > x_tolerance:
                continue
            if _vertical_overlap_ratio(box, existing) >= 0.2:
                continue
            max_distance = cross_band_max_distance_height_ratio * max(
                _height(box), _height(existing)
            )
            if abs(_center_y(existing) - _center_y(box)) <= max_distance:
                select(item, "aligned_existing")
                break

    for existing in normalized_existing:
        existing_width = _width(existing)
        refinements = []
        for item in eligible:
            box = _box(item["bbox"])
            if existing_width < max(12.0, wide_seed_width_ratio * _width(box)):
                continue
            if _vertical_overlap_ratio(box, existing) < 0.5:
                continue
            if abs(_center_x(existing) - _center_x(box)) <= max(
                float(x_tolerance), existing_width / 2.0
            ):
                refinements.append(item)
        if refinements:
            best = max(
                refinements,
                key=lambda item: (
                    float(item.get("ink_ratio", 0.0)),
                    -abs(_center_x(_box(item["bbox"])) - _center_x(existing)),
                ),
            )
            select(best, "wide_seed_refinement")

    rescued_boxes = sorted(selected)
    rescued_set = set(rescued_boxes)
    remaining = [
        dict(item)
        for item in dropped
        if not isinstance(item.get("bbox"), Sequence) or _box(item["bbox"]) not in rescued_set
    ]
    details = [
        {
            "bbox": list(box),
            "supports": sorted(supports[box]),
            "ink_ratio": float(selected[box].get("ink_ratio", 0.0)),
        }
        for box in rescued_boxes
    ]
    return rescued_boxes, remaining, details
