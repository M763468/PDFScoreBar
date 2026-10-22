"""Manual correction helpers for pipeline override payloads.

This module keeps three correction responsibilities separate:

- MMR measure-span correction for already-created measures.
- Measure-construction correction for interval-level numbering exceptions.
- Barline-construction correction for missing or extra detected barlines.

MMR measure-span correction intentionally does not alter barlines, staves,
systems, or measure intervals. Future grouping/divisi operations are also kept
outside this narrow MMR path until they have a dedicated implementation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

MeasureOverride = Dict[str, Any]
BarlineOverride = Dict[str, Any]
Payload = Dict[str, Any]


OverrideKey = Tuple[Optional[int], Optional[int], Optional[int]]


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _measure_key(item: Dict[str, Any]) -> OverrideKey:
    return (
        _to_int_or_none(item.get("page")),
        _to_int_or_none(item.get("system")),
        _to_int_or_none(item.get("measure")),
    )


def _normalise_measure_override(item: Dict[str, Any]) -> MeasureOverride:
    override = deepcopy(item)
    for key in ("page", "system", "measure", "skip", "set_number"):
        if key in override and override[key] is not None:
            try:
                override[key] = int(override[key])
            except (TypeError, ValueError):
                pass
    return override


def _normalise_barline_override(item: Dict[str, Any]) -> BarlineOverride:
    override = deepcopy(item)
    if "page" in override and override["page"] is not None:
        try:
            override["page"] = int(override["page"])
        except (TypeError, ValueError):
            pass
    if "bbox" in override and isinstance(override["bbox"], list):
        override["bbox"] = [int(value) for value in override["bbox"]]
    return override


def normalise_measure_overrides(payload: Optional[Payload]) -> List[MeasureOverride]:
    """Return legacy or current measure overrides as a normalized list.

    Supported payloads:

    - {"measure_overrides": [...]}: current pipeline shape.
    - {"overrides": [...]}: legacy/debug shape still produced by older helpers.
    """
    if not payload:
        return []
    for key in ("measure_overrides", "overrides"):
        records = payload.get(key)
        if isinstance(records, list):
            return [_normalise_measure_override(item) for item in records if isinstance(item, dict)]
    return []


def normalise_barline_overrides(payload: Optional[Payload]) -> List[BarlineOverride]:
    """Return barline overrides as a normalized list."""
    if not payload:
        return []
    records = payload.get("barline_overrides")
    if not isinstance(records, list):
        return []
    return [_normalise_barline_override(item) for item in records if isinstance(item, dict)]


def _manual_comment(item: Dict[str, Any], default: str) -> str:
    return str(item.get("comment") or item.get("reason") or default)


def _bbox(item: Dict[str, Any]) -> List[int]:
    bbox = item.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("barline manual corrections require a 4-value bbox")
    return [int(value) for value in bbox]


def _set_measure_span_override(item: Dict[str, Any]) -> MeasureOverride:
    measure_span = int(item["measure_span"])
    if measure_span < 1:
        raise ValueError("MMR measure_span manual corrections must be >= 1")
    override: MeasureOverride = {
        "page": int(item["page"]),
        "system": int(item["system"]),
        "measure": int(item["measure"]),
        "skip": measure_span - 1,
        "comment": _manual_comment(item, f"manual MMR measure_span={measure_span}"),
        "source": item.get("source", "manual:mmr_measure_span"),
    }
    if "set_number" in item and item["set_number"] is not None:
        override["set_number"] = int(item["set_number"])
    return override


def apply_mmr_measure_span_corrections(
    overrides: Iterable[MeasureOverride], correction_payload: Payload
) -> List[MeasureOverride]:
    """Apply manual MMR measure-span corrections to existing overrides.

    Supported item operations:

    - suppress: remove an existing override at page/system/measure.
    - set_measure_span: replace or add the override at page/system/measure.

    `measure_span` is the number of measures represented by the visible
    multi-measure rest mark. It is not a count of rest glyphs. The conversion to
    `skip = measure_span - 1` is valid only when measure construction has already
    created the target measure correctly.
    """
    result = [deepcopy(item) for item in overrides]
    items = correction_payload.get("items", [])
    if not isinstance(items, list):
        return result

    for item in items:
        if not isinstance(item, dict):
            continue
        op = item.get("op")
        if op not in {"suppress", "set_measure_span"}:
            continue
        try:
            key = (int(item["page"]), int(item["system"]), int(item["measure"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid page/system/measure in correction item: {item}") from exc
        result = [override for override in result if _measure_key(override) != key]
        if op == "set_measure_span":
            result.append(_set_measure_span_override(item))
    return result


def measure_construction_overrides(
    correction_payload: Payload,
) -> List[MeasureOverride]:
    """Translate supported measure-construction manual corrections.

    The current narrow implementation supports only interval-level
    `force_measure`. Future grouping/divisi operations such as
    `group_staves_as_system` are deliberately ignored here so they cannot be
    confused with MMR measure-span corrections.
    """
    items = correction_payload.get("items", [])
    if not isinstance(items, list):
        return []

    overrides: List[MeasureOverride] = []
    for item in items:
        if not isinstance(item, dict) or item.get("op") != "force_measure":
            continue
        try:
            page = int(item["page"])
            system = int(item["system"])
            measure = int(item["interval"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid page/system/interval in force_measure item: {item}") from exc
        override: MeasureOverride = {
            "page": page,
            "system": system,
            "measure": measure,
            "force_measure": True,
            "comment": _manual_comment(item, "manual measure-construction force_measure"),
            "source": item.get("source", "manual:measure_construction"),
        }
        if "skip" in item and item["skip"] is not None:
            override["skip"] = int(item["skip"])
        if "set_number" in item and item["set_number"] is not None:
            override["set_number"] = int(item["set_number"])
        overrides.append(override)
    return overrides


def barline_construction_overrides(
    correction_payload: Payload,
) -> List[BarlineOverride]:
    """Translate supported barline-construction manual corrections.

    Supported item operations:

    - add_barline: add a missing detected barline bbox.
    - remove_barline: remove an extra detected barline by bbox matching.
    """
    items = correction_payload.get("items", [])
    if not isinstance(items, list):
        return []

    overrides: List[BarlineOverride] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        op = item.get("op")
        if op not in {"add_barline", "remove_barline"}:
            continue
        overrides.append(
            {
                "page": int(item["page"]),
                "op": "add" if op == "add_barline" else "remove",
                "bbox": _bbox(item),
                "comment": _manual_comment(item, f"manual {op}"),
                "source": item.get("source", "manual:barline_construction"),
            }
        )
    return overrides


def merge_measure_overrides(*payloads: Optional[Payload]) -> Payload:
    """Merge auto MMR, manual MMR, and measure-construction overrides.

    The returned payload includes both `measure_overrides` and `overrides` for
    compatibility with current final-numbering code and older debug helpers.
    """
    auto_or_legacy: List[MeasureOverride] = []
    mmr_measure_span_payloads: List[Payload] = []
    measure_construction_payloads: List[Payload] = []

    for payload in payloads:
        if not payload:
            continue
        correction_type = payload.get("correction_type")
        if correction_type == "mmr_measure_span":
            mmr_measure_span_payloads.append(payload)
        elif correction_type == "measure_construction":
            measure_construction_payloads.append(payload)
        elif correction_type == "barline_construction":
            continue
        else:
            auto_or_legacy.extend(normalise_measure_overrides(payload))

    merged: List[MeasureOverride] = auto_or_legacy
    for payload in measure_construction_payloads:
        merged.extend(measure_construction_overrides(payload))
    for payload in mmr_measure_span_payloads:
        merged = apply_mmr_measure_span_corrections(merged, payload)

    return {"measure_overrides": merged, "overrides": deepcopy(merged)}


def merge_barline_overrides(*payloads: Optional[Payload]) -> Payload:
    """Merge manual and existing barline override payloads."""
    merged: List[BarlineOverride] = []
    for payload in payloads:
        if not payload:
            continue
        if payload.get("correction_type") == "barline_construction":
            merged.extend(barline_construction_overrides(payload))
        else:
            merged.extend(normalise_barline_overrides(payload))
    return {"barline_overrides": merged}
