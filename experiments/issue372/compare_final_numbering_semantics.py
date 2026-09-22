#!/usr/bin/env python3
"""Compare Issue #372 final measure-numbering semantics between two runs.

Detector geometry is diagnostic. Acceptance-relevant differences are:
- system count;
- ordered per-system physical measure counts;
- serialized measure-number sequence;
- page final/next numbering state when present.

BBox-only differences are reported separately and do not by themselves fail the
logical numbering gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _one_page(path: Path) -> Mapping[str, Any]:
    payload = _load(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one serialized page: {path}")
    return pages[0]


def _measure_numbers(system: Mapping[str, Any]) -> list[Any]:
    measures = system.get("measures", [])
    if not isinstance(measures, list):
        raise ValueError("system.measures must be a list")
    return [
        measure.get("number") if isinstance(measure, Mapping) else None
        for measure in measures
    ]


def _measure_geometry(system: Mapping[str, Any]) -> list[Any]:
    measures = system.get("measures", [])
    return [
        measure.get("bbox") if isinstance(measure, Mapping) else None
        for measure in measures
    ]


def page_signature(path: Path) -> dict[str, Any]:
    page = _one_page(path)
    systems_raw = page.get("systems", [])
    if not isinstance(systems_raw, list):
        raise ValueError(f"Expected systems list: {path}")
    systems = [system for system in systems_raw if isinstance(system, Mapping)]
    metadata = _load(path).get("numbering_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    return {
        "system_count": len(systems),
        "measure_counts": [len(system.get("measures", [])) for system in systems],
        "number_sequences": [_measure_numbers(system) for system in systems],
        "measure_geometry": [_measure_geometry(system) for system in systems],
        "empty_system_count": len(page.get("empty_systems", []) or []),
        "metadata": {
            "start_number": metadata.get("start_number"),
            "next_number": metadata.get("next_number"),
            "movement_boundaries": metadata.get("movement_boundaries"),
        },
    }


def collect(run_dir: Path, *, stage: str) -> dict[str, dict[str, Any]]:
    intermediate = run_dir / "intermediate"
    if not intermediate.is_dir():
        raise FileNotFoundError(intermediate)
    rows: dict[str, dict[str, Any]] = {}
    for page_dir in sorted(p for p in intermediate.glob("page_*") if p.is_dir()):
        path = page_dir / f"{stage}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        rows[page_dir.name] = page_signature(path)
    if not rows:
        raise ValueError(f"No page_* directories under {intermediate}")
    return rows


def compare(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    baseline_pages = set(baseline)
    candidate_pages = set(candidate)
    missing = sorted(baseline_pages - candidate_pages)
    added = sorted(candidate_pages - baseline_pages)

    logical_changes: list[dict[str, Any]] = []
    geometry_only_changes: list[dict[str, Any]] = []
    exact_pages = 0

    for page_id in sorted(baseline_pages & candidate_pages):
        left = baseline[page_id]
        right = candidate[page_id]
        logical_equal = (
            left["system_count"] == right["system_count"]
            and left["measure_counts"] == right["measure_counts"]
            and left["number_sequences"] == right["number_sequences"]
            and left["empty_system_count"] == right["empty_system_count"]
            and left["metadata"] == right["metadata"]
        )
        geometry_equal = left["measure_geometry"] == right["measure_geometry"]

        if logical_equal and geometry_equal:
            exact_pages += 1
            continue
        row = {
            "page_id": page_id,
            "baseline": left,
            "candidate": right,
        }
        if logical_equal:
            geometry_only_changes.append(row)
        else:
            logical_changes.append(row)

    return {
        "schema_version": "issue372.final_numbering_semantics.v1",
        "logical_numbering_match": not missing and not added and not logical_changes,
        "baseline_pages": len(baseline),
        "candidate_pages": len(candidate),
        "missing_pages": missing,
        "added_pages": added,
        "logical_changed_page_count": len(logical_changes),
        "geometry_only_changed_page_count": len(geometry_only_changes),
        "exactly_unchanged_page_count": exact_pages,
        "logical_changed_pages": logical_changes,
        "geometry_only_changed_pages": geometry_only_changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--stage", default="numbering_final")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = compare(
        collect(args.baseline_run.resolve(), stage=args.stage),
        collect(args.candidate_run.resolve(), stage=args.stage),
    )
    report.update(
        {
            "baseline_run": str(args.baseline_run.resolve()),
            "candidate_run": str(args.candidate_run.resolve()),
            "stage": args.stage,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "logical_numbering_match": report["logical_numbering_match"],
                "logical_changed_page_count": report["logical_changed_page_count"],
                "geometry_only_changed_page_count": report["geometry_only_changed_page_count"],
                "exactly_unchanged_page_count": report["exactly_unchanged_page_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["logical_numbering_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
