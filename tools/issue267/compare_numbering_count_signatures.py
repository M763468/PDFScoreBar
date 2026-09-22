#!/usr/bin/env python3
"""Compare physical-measure counts and diagnose semantic numbering geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_signature(path: Path) -> dict[str, Any]:
    """Return serialized system/measure/staff geometry for a one-page payload."""
    payload = _load_json(path)
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError(
            f"Expected one page in {path}, got {0 if not isinstance(pages, list) else len(pages)}"
        )

    page = pages[0]
    systems = page.get("systems", [])
    empty_systems = page.get("empty_systems", [])
    if not isinstance(systems, list):
        raise ValueError(f"Expected systems list in {path}")
    if not isinstance(empty_systems, list):
        raise ValueError(f"Expected empty_systems list in {path}")

    return {
        "systems": systems,
        "empty_systems": empty_systems,
    }


def _count_signature(signature: dict[str, Any]) -> list[int]:
    return [len(system.get("measures", [])) for system in signature["systems"]]


def _total_measures(signature: dict[str, Any]) -> int:
    return sum(_count_signature(signature))


def collect_run_signatures(
    run_dir: Path, *, stage: str = "numbering_base"
) -> dict[str, dict[str, Any]]:
    """Collect ordered semantic page signatures from a pipeline run directory."""
    intermediate = run_dir / "intermediate"
    if not intermediate.is_dir():
        raise FileNotFoundError(f"Missing intermediate directory: {intermediate}")

    result: dict[str, dict[str, Any]] = {}
    for page_dir in sorted(path for path in intermediate.glob("page_*") if path.is_dir()):
        payload = page_dir / f"{stage}.json"
        if not payload.is_file():
            raise FileNotFoundError(f"Missing {stage} payload: {payload}")
        result[page_dir.name] = semantic_signature(payload)
    if not result:
        raise ValueError(f"No page directories found under {intermediate}")
    return result


def compare_signatures(
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare count acceptance and retain exact geometry differences as diagnostics."""
    baseline_pages = set(baseline)
    candidate_pages = set(candidate)
    missing = sorted(baseline_pages - candidate_pages)
    added = sorted(candidate_pages - baseline_pages)

    count_changed = []
    geometry_changed = []
    for page_id in sorted(baseline_pages & candidate_pages):
        baseline_counts = _count_signature(baseline[page_id])
        candidate_counts = _count_signature(candidate[page_id])
        if baseline_counts != candidate_counts:
            count_changed.append(
                {
                    "page_id": page_id,
                    "baseline_counts": baseline_counts,
                    "candidate_counts": candidate_counts,
                    "baseline_total": _total_measures(baseline[page_id]),
                    "candidate_total": _total_measures(candidate[page_id]),
                }
            )
        if baseline[page_id] != candidate[page_id]:
            geometry_changed.append(
                {
                    "page_id": page_id,
                    "counts_equal": baseline_counts == candidate_counts,
                    "baseline_counts": baseline_counts,
                    "candidate_counts": candidate_counts,
                    "baseline_total": _total_measures(baseline[page_id]),
                    "candidate_total": _total_measures(candidate[page_id]),
                    "baseline_geometry": baseline[page_id],
                    "candidate_geometry": candidate[page_id],
                }
            )

    baseline_total = sum(_total_measures(signature) for signature in baseline.values())
    candidate_total = sum(_total_measures(signature) for signature in candidate.values())
    count_match = not missing and not added and not count_changed
    semantic_match = not missing and not added and not geometry_changed

    return {
        "comparison": "physical_measure_counts_with_semantic_diagnostics",
        # Acceptance for Issue #267 is physical-measure counting. Keep exact_match
        # as the CLI-compatible acceptance alias while exposing semantic_match
        # separately so harmless BBox drift remains reviewable rather than hidden.
        "exact_match": count_match,
        "count_match": count_match,
        "semantic_match": semantic_match,
        "baseline_pages": len(baseline),
        "candidate_pages": len(candidate),
        "baseline_total_measures": baseline_total,
        "candidate_total_measures": candidate_total,
        "total_measure_delta": candidate_total - baseline_total,
        "missing_pages": missing,
        "added_pages": added,
        "count_changed_pages": count_changed,
        "geometry_changed_pages": geometry_changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--stage", default="numbering_base")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = compare_signatures(
        collect_run_signatures(args.baseline_run, stage=args.stage),
        collect_run_signatures(args.candidate_run, stage=args.stage),
    )
    report["baseline_run"] = str(args.baseline_run)
    report["candidate_run"] = str(args.candidate_run)
    report["stage"] = args.stage

    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["count_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
