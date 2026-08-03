#!/usr/bin/env python3
"""Inventory and compare historical vs fresh Stage E upstream artifacts.

This is an offline restoration analysis. It does not run HOMR, SR, OMR-DLN,
probe generation, filtering, CNN inference, or detector evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
JSON_SUFFIXES = {".json"}


def _resolve(path: str | Path, root: Path) -> Path:
    value = Path(path)
    if value.is_absolute() and value.parts[:2] == ("/", "workspace"):
        return root / value.relative_to("/workspace")
    return value if value.is_absolute() else root / value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    records: Any = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return None
    boxes: list[tuple[int, int, int, int]] = []
    for item in records:
        bbox: Any = item
        if isinstance(item, dict):
            bbox = item.get("bbox", item.get("pred_bbox"))
        if isinstance(bbox, list) and len(bbox) >= 4:
            try:
                boxes.append(tuple(int(round(float(value))) for value in bbox[:4]))
            except (TypeError, ValueError):
                return None
        else:
            return None
    return boxes


def _classify(path: Path) -> str:
    lowered = path.as_posix().lower()
    name = path.name.lower()
    if "hybrid" in name and path.suffix.lower() == ".json":
        return "hybrid"
    if "omr" in lowered and path.suffix.lower() == ".json":
        return "omr"
    if "/sr/" in lowered and path.suffix.lower() == ".json":
        return "sr"
    if "/baseline/" in lowered and path.suffix.lower() == ".json":
        return "baseline"
    if "clef" in name and path.suffix.lower() in IMAGE_SUFFIXES:
        return "clef_mask"
    if "staff" in name and path.suffix.lower() in IMAGE_SUFFIXES:
        return "staff_mask"
    return "other"


def _record(path: Path, base: Path) -> dict[str, Any]:
    boxes = _load_boxes(path) if path.suffix.lower() in JSON_SUFFIXES else None
    return {
        "path": str(path),
        "relative_path": path.relative_to(base).as_posix(),
        "kind": _classify(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "box_count": len(boxes) if boxes is not None else None,
    }


def _inventory(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES | JSON_SUFFIXES
    )
    return [_record(path, root) for path in files]


def _by_kind(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(str(row["kind"]), []).append(row)
    return result


def _page_report(
    *,
    page_key: str,
    page: dict[str, Any],
    source_run: Path,
    repo_root: Path,
) -> dict[str, Any]:
    historical_record = page["historical_inventory_record"]
    historical_run = _resolve(historical_record["run_dir"], repo_root)
    fresh_snapshot = source_run / "fresh_source_snapshot" / page["score"] / page["page"]
    historical_rows = _inventory(historical_run)
    fresh_rows = _inventory(fresh_snapshot)
    return {
        "label": page_key,
        "score": page["score"],
        "page": page["page"],
        "historical_run": str(historical_run),
        "fresh_snapshot": str(fresh_snapshot),
        "historical_file_count": len(historical_rows),
        "fresh_file_count": len(fresh_rows),
        "historical_by_kind": _by_kind(historical_rows),
        "fresh_by_kind": _by_kind(fresh_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    source_run = _resolve(comparison["source_run"], args.repo_root.resolve())
    pages = comparison.get("pages")
    if not isinstance(pages, dict):
        raise ValueError("comparison.pages must be an object")
    report = {
        "schema_version": "issue255.stage_e_historical_upstream_inventory.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "next_gpu_run_required": False,
        "source_comparison": str(args.comparison.resolve()),
        "source_run": str(source_run),
        "pages": {
            key: _page_report(
                page_key=key,
                page=value,
                source_run=source_run,
                repo_root=args.repo_root.resolve(),
            )
            for key, value in pages.items()
        },
    }
    output = args.output or source_run / "stage_e_historical_upstream_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(output)}))


if __name__ == "__main__":
    main()
