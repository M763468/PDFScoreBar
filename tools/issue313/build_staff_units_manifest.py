#!/usr/bin/env python3
"""Materialize page-level staff-unit provenance from the Issue #313 audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from src.common.barline_units import STAFF_UNITS_SCHEMA_VERSION


def _page_key(group: str) -> str:
    score, suffix = group.rsplit("_page_", 1)
    return f"{score}/page_{suffix}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_source_path(score: str, page: str) -> str:
    return f"external://issue313-phase1/homr_staff_mask/{score}/{page}_staff_mask.png"


def build_manifest(audit_path: Path) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    pages: dict[str, dict[str, Any]] = {}
    for entry in audit["pages"]:
        mask_path = Path(entry["geometry"]["mask"])
        if not mask_path.is_file():
            raise FileNotFoundError(f"Missing audited staff mask: {mask_path}")
        with Image.open(mask_path) as image:
            width, height = image.size
        key = _page_key(entry["group"])
        score, page = key.split("/", 1)
        pages[key] = {
            "unit_size": entry["unit_size"],
            "coordinate_width": width,
            "coordinate_height": height,
            "source_kind": "homr_staff_mask_snapshot",
            "source_path": _portable_source_path(score, page),
            "source_sha256": _sha256(mask_path),
        }
    return {"schema_version": STAFF_UNITS_SCHEMA_VERSION, "pages": pages}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_manifest(args.audit_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(manifest['pages'])} staff-unit entries: {args.output}")


if __name__ == "__main__":
    main()
