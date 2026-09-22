#!/usr/bin/env python3
"""Compare physical-measure count signatures between two numbering runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def physical_signature(path: Path) -> list[int]:
    """Return per-system physical measure counts for a one-page numbering payload."""
    payload = _load_json(path)
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError(
            f"Expected one page in {path}, got {0 if not isinstance(pages, list) else len(pages)}"
        )
    systems = pages[0].get("systems", [])
    if not isinstance(systems, list):
        raise ValueError(f"Expected systems list in {path}")
    return [len(system.get("measures", [])) for system in systems]


def collect_run_signatures(run_dir: Path, *, stage: str = "numbering_base") -> dict[str, list[int]]:
    """Collect ordered page signatures from a pipeline run directory."""
    intermediate = run_dir / "intermediate"
    if not intermediate.is_dir():
        raise FileNotFoundError(f"Missing intermediate directory: {intermediate}")

    result: dict[str, list[int]] = {}
    for page_dir in sorted(path for path in intermediate.glob("page_*") if path.is_dir()):
        payload = page_dir / f"{stage}.json"
        if not payload.is_file():
            raise FileNotFoundError(f"Missing {stage} payload: {payload}")
        result[page_dir.name] = physical_signature(payload)
    if not result:
        raise ValueError(f"No page directories found under {intermediate}")
    return result


def compare_signatures(
    baseline: dict[str, list[int]], candidate: dict[str, list[int]]
) -> dict[str, Any]:
    """Compare exact page/system physical-measure count signatures."""
    baseline_pages = set(baseline)
    candidate_pages = set(candidate)
    missing = sorted(baseline_pages - candidate_pages)
    added = sorted(candidate_pages - baseline_pages)

    changed = []
    for page_id in sorted(baseline_pages & candidate_pages):
        if baseline[page_id] != candidate[page_id]:
            changed.append(
                {
                    "page_id": page_id,
                    "baseline": baseline[page_id],
                    "candidate": candidate[page_id],
                    "baseline_total": sum(baseline[page_id]),
                    "candidate_total": sum(candidate[page_id]),
                }
            )

    baseline_total = sum(sum(counts) for counts in baseline.values())
    candidate_total = sum(sum(counts) for counts in candidate.values())
    exact_match = not missing and not added and not changed

    return {
        "exact_match": exact_match,
        "baseline_pages": len(baseline),
        "candidate_pages": len(candidate),
        "baseline_total_measures": baseline_total,
        "candidate_total_measures": candidate_total,
        "total_measure_delta": candidate_total - baseline_total,
        "missing_pages": missing,
        "added_pages": added,
        "changed_pages": changed,
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
    return 0 if report["exact_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
