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
BOX_STAGES = ("baseline", "sr", "omr", "hybrid")


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
    if name == "baseline.json":
        return "baseline"
    if name == "sr.json":
        return "sr"
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


def _single_box_record(rows: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    matches = [row for row in rows if row["kind"] == kind and row["box_count"] is not None]
    return matches[0] if len(matches) == 1 else None


def _box_stage_comparison(
    historical_rows: list[dict[str, Any]],
    fresh_rows: list[dict[str, Any]],
    kind: str,
) -> dict[str, Any] | None:
    historical = _single_box_record(historical_rows, kind)
    fresh = _single_box_record(fresh_rows, kind)
    if historical is None or fresh is None:
        return None
    historical_boxes = set(_load_boxes(Path(historical["path"])) or [])
    fresh_boxes = set(_load_boxes(Path(fresh["path"])) or [])
    return {
        "historical_path": historical["path"],
        "fresh_path": fresh["path"],
        "historical_count": len(historical_boxes),
        "fresh_count": len(fresh_boxes),
        "exact_common_count": len(historical_boxes & fresh_boxes),
        "historical_only_count": len(historical_boxes - fresh_boxes),
        "fresh_only_count": len(fresh_boxes - historical_boxes),
        "exact_match": historical_boxes == fresh_boxes,
    }


def _json_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "content": json.loads(path.read_text(encoding="utf-8")),
    }


def _historical_homr_contracts(historical_run: Path, page: str) -> dict[str, dict[str, Any] | None]:
    result: dict[str, dict[str, Any] | None] = {}
    for stage in ("baseline", "sr"):
        stage_root = historical_run / stage / page
        run_config = stage_root / "run_config.json"
        metrics = stage_root / "metrics.json"
        result[stage] = {
            "run_config": _json_record(run_config) if run_config.is_file() else None,
            "metrics": _json_record(metrics) if metrics.is_file() else None,
        }
    return result


def _replace_path_part(path: Path, old: str, new: str) -> Path:
    parts = list(path.parts)
    try:
        index = parts.index(old)
    except ValueError:
        return path
    parts[index] = new
    return Path(*parts)


def _find_fresh_metadata(run_dir: Path, page: str, filename: str) -> Path | None:
    roots = [run_dir, run_dir.parent, run_dir.parent.parent]
    matches: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        direct = root / filename
        if direct.is_file():
            matches.add(direct.resolve())
        for candidate in root.glob(f"**/{filename}"):
            if page in candidate.as_posix():
                matches.add(candidate.resolve())
    return next(iter(matches)) if len(matches) == 1 else None


def _fresh_homr_contracts(fresh_run_dir: Path, page: str) -> dict[str, dict[str, Any] | None]:
    result: dict[str, dict[str, Any] | None] = {}
    for stage, run_dir in (
        ("baseline", fresh_run_dir),
        ("sr", _replace_path_part(fresh_run_dir, "baseline", "sr")),
    ):
        result[stage] = {}
        for filename in ("run_config.json", "metrics.json"):
            path = _find_fresh_metadata(run_dir, page, filename)
            result[stage][filename.removesuffix(".json")] = (
                _json_record(path) if path is not None else None
            )
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
    stage_comparisons = {
        kind: _box_stage_comparison(historical_rows, fresh_rows, kind) for kind in BOX_STAGES
    }
    first_persisted_divergence = next(
        (
            kind
            for kind in BOX_STAGES
            if stage_comparisons[kind] is not None and not stage_comparisons[kind]["exact_match"]
        ),
        None,
    )
    fresh_run_dir = _resolve(page["fresh_inventory_record"]["run_dir"], repo_root)
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
        "box_stage_comparisons": stage_comparisons,
        "first_persisted_divergence": first_persisted_divergence,
        "historical_homr_contracts": _historical_homr_contracts(historical_run, page["page"]),
        "fresh_homr_contracts": _fresh_homr_contracts(fresh_run_dir, page["page"]),
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
        "schema_version": "issue255.stage_e_historical_upstream_inventory.v2",
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
    report["conclusion"] = {
        "first_persisted_divergence": {
            key: value["first_persisted_divergence"] for key, value in report["pages"].items()
        },
        "new_recovery_direction_introduced": False,
    }
    output = args.output or source_run / "stage_e_historical_upstream_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(output)}))


if __name__ == "__main__":
    main()
