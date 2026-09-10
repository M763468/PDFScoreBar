"""Validated staff-unit metadata for normalized barline matching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

STAFF_UNITS_SCHEMA_VERSION = "barline_staff_units.v1"


@dataclass(frozen=True)
class PageStaffUnit:
    """Staff spacing and provenance in the exact box coordinate frame."""

    unit_size: float
    coordinate_width: int
    coordinate_height: int
    source_kind: str
    source_path: str
    source_sha256: str


def page_key(score: str, page: str) -> str:
    return f"{score}/{page}"


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _parse_page_unit(key: str, value: Any) -> PageStaffUnit:
    data = _require_mapping(value, label=f"pages[{key!r}]")
    try:
        unit_size = float(data["unit_size"])
        width = int(data["coordinate_width"])
        height = int(data["coordinate_height"])
        source_kind = str(data["source_kind"])
        source_path = str(data["source_path"])
        source_sha256 = str(data["source_sha256"])
    except KeyError as exc:
        raise ValueError(f"pages[{key!r}] lacks {exc.args[0]!r}") from exc
    if not unit_size > 0:
        raise ValueError(f"pages[{key!r}].unit_size must be positive")
    if width <= 0 or height <= 0:
        raise ValueError(f"pages[{key!r}] coordinate dimensions must be positive")
    if not source_kind or not source_path or len(source_sha256) != 64:
        raise ValueError(f"pages[{key!r}] has incomplete provenance")
    return PageStaffUnit(unit_size, width, height, source_kind, source_path, source_sha256)


def load_page_staff_units(path: Path) -> dict[str, PageStaffUnit]:
    """Load a source-qualified page-unit manifest without geometry guessing."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Unable to read staff-unit manifest: {path}") from exc
    data = _require_mapping(payload, label="staff-unit manifest")
    if data.get("schema_version") != STAFF_UNITS_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported staff-unit schema: {data.get('schema_version')!r}; "
            f"expected {STAFF_UNITS_SCHEMA_VERSION!r}"
        )
    pages = _require_mapping(data.get("pages"), label="staff-unit manifest.pages")
    if not pages:
        raise ValueError("staff-unit manifest.pages must not be empty")
    return {str(key): _parse_page_unit(str(key), value) for key, value in pages.items()}


def require_page_staff_unit(
    units: Mapping[str, PageStaffUnit], score: str, page: str
) -> PageStaffUnit:
    key = page_key(score, page)
    try:
        return units[key]
    except KeyError as exc:
        raise ValueError(f"Staff-unit manifest has no entry for {key}") from exc
