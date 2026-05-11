#!/usr/bin/env python3
"""Compare candidate coverage between two Issue #120 candidate trees."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import find_page_file, iter_manifest  # noqa: E402


def load_count(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload: Any = json.load(f)
    if not isinstance(payload, list):
        return None
    return len(payload)


def safe_ratio(num: int | None, den: int | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"),
        help="Reference candidate tree.",
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=Path("logs/repro_v12_recovery_final/probe_candidates_filtered_v12"),
        help="Candidate tree to compare against baseline.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_seed_regen_eval"),
    )
    parser.add_argument("--candidate-file", default="pipeline2_no_peak_candidates.json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = iter_manifest()

    rows: list[dict[str, Any]] = []
    baseline_total = 0
    candidate_total = 0
    missing_baseline = 0
    missing_candidate = 0
    empty_candidate_pages = 0

    for record in manifest:
        baseline_path = find_page_file(args.baseline_dir, record, args.candidate_file)
        candidate_path = find_page_file(args.candidate_dir, record, args.candidate_file)
        baseline_count = load_count(baseline_path)
        candidate_count = load_count(candidate_path)

        if baseline_count is None:
            missing_baseline += 1
        else:
            baseline_total += baseline_count
        if candidate_count is None:
            missing_candidate += 1
        else:
            candidate_total += candidate_count
            if candidate_count == 0:
                empty_candidate_pages += 1

        rows.append(
            {
                "score": record.score,
                "page": record.page,
                "baseline_count": baseline_count,
                "candidate_count": candidate_count,
                "delta": None
                if baseline_count is None or candidate_count is None
                else candidate_count - baseline_count,
                "candidate_to_baseline_ratio": safe_ratio(candidate_count, baseline_count),
                "baseline_path": str(baseline_path) if baseline_path else None,
                "candidate_path": str(candidate_path) if candidate_path else None,
            }
        )

    summary = {
        "schema_version": "issue120.candidate_coverage_comparison.v1",
        "baseline_dir": str(args.baseline_dir),
        "candidate_dir": str(args.candidate_dir),
        "expected_pages": len(manifest),
        "baseline_total_candidates": baseline_total,
        "candidate_total_candidates": candidate_total,
        "total_delta": candidate_total - baseline_total,
        "candidate_to_baseline_ratio": safe_ratio(candidate_total, baseline_total),
        "missing_baseline_pages": missing_baseline,
        "missing_candidate_pages": missing_candidate,
        "empty_candidate_pages": empty_candidate_pages,
        "worst_pages": sorted(
            rows,
            key=lambda r: (
                r["candidate_to_baseline_ratio"]
                if r["candidate_to_baseline_ratio"] is not None
                else -1
            ),
        )[:20],
    }

    (args.output_dir / "candidate_coverage_comparison.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (args.output_dir / "candidate_coverage_comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("Candidate coverage comparison")
    print(f"Pages: {len(manifest)}")
    print(f"Baseline candidates: {baseline_total}")
    print(f"Compared candidates: {candidate_total}")
    print(f"Ratio: {safe_ratio(candidate_total, baseline_total)}")
    print(f"Empty compared pages: {empty_candidate_pages}")
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
