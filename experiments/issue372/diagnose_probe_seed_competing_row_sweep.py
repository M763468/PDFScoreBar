#!/usr/bin/env python3
"""Sweep retained competing-row geometry for Issue #372 singleton probe seeds.

Consumes diagnose_probe_seed_competing_rows.py output only. No inference,
candidate regeneration, or production code execution is performed.

The goal is to quantify whether a simple row-level competition rule can suppress
false singleton probe authorities while preserving useful true singleton rows.
This diagnostic intentionally does not select a production threshold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def run(report_path: Path) -> dict[str, Any]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "issue372.probe_seed_competing_row.v1":
        raise ValueError(f"Unexpected schema: {payload.get('schema_version')!r}")

    rows = [
        *payload.get("true_singletons", []),
        *payload.get("false_singletons", []),
    ]

    thresholds = [20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 100, 120, 150, 180, 200]

    def evaluate(max_gap: float, require_overlap: bool) -> dict[str, Any]:
        suppressed = []
        kept = []
        for row in rows:
            nearest = row.get("nearest_multi")
            conflict = False
            if nearest is not None:
                conflict = float(nearest["center_gap"]) <= max_gap
                if require_overlap:
                    conflict = conflict and float(nearest["overlap_px"]) > 0.0
            (suppressed if conflict else kept).append(row)

        def stats(group: list[dict[str, Any]]) -> dict[str, int]:
            return {
                "rows": len(group),
                "gt_true_rows": sum(r["row_gt_class"] == "gt_true" for r in group),
                "gt_false_rows": sum(r["row_gt_class"] == "gt_false" for r in group),
                "useful_true_rows": sum(
                    r["row_gt_class"] == "gt_true"
                    and int(r["generated_distinct_gt_count"]) > 0
                    for r in group
                ),
                "generated_distinct_gt_from_true_rows": sum(
                    int(r["generated_distinct_gt_count"])
                    for r in group
                    if r["row_gt_class"] == "gt_true"
                ),
                "generated_candidates_from_false_rows": sum(
                    int(r["generated_count"])
                    for r in group
                    if r["row_gt_class"] == "gt_false"
                ),
            }

        return {
            "max_center_gap": max_gap,
            "require_vertical_overlap": require_overlap,
            "suppressed": stats(suppressed),
            "kept": stats(kept),
            "suppressed_rows": suppressed,
        }

    sweeps = []
    for overlap in (False, True):
        for gap in thresholds:
            sweeps.append(evaluate(gap, overlap))

    x4_only_rows = [r for r in rows if r["row_support_class"] == "x4_only"]
    x4_only_sweeps = []
    for gap in thresholds:
        suppressed = []
        kept = []
        for row in x4_only_rows:
            nearest = row.get("nearest_multi")
            conflict = (
                nearest is not None
                and float(nearest["center_gap"]) <= gap
                and float(nearest["overlap_px"]) > 0.0
            )
            (suppressed if conflict else kept).append(row)

        x4_only_sweeps.append(
            {
                "max_center_gap": gap,
                "suppressed_false_rows": sum(r["row_gt_class"] == "gt_false" for r in suppressed),
                "suppressed_true_rows": sum(r["row_gt_class"] == "gt_true" for r in suppressed),
                "suppressed_useful_true_rows": sum(
                    r["row_gt_class"] == "gt_true"
                    and int(r["generated_distinct_gt_count"]) > 0
                    for r in suppressed
                ),
                "suppressed_false_generated_candidates": sum(
                    int(r["generated_count"])
                    for r in suppressed
                    if r["row_gt_class"] == "gt_false"
                ),
                "lost_distinct_gt_from_true_rows": sum(
                    int(r["generated_distinct_gt_count"])
                    for r in suppressed
                    if r["row_gt_class"] == "gt_true"
                ),
                "kept_false_rows": sum(r["row_gt_class"] == "gt_false" for r in kept),
                "kept_true_rows": sum(r["row_gt_class"] == "gt_true" for r in kept),
            }
        )

    print("=== x4-only singleton competition sweep ===")
    for row in x4_only_sweeps:
        print(
            f"gap<={row['max_center_gap']:>3}: "
            f"false_suppressed={row['suppressed_false_rows']:>2} "
            f"true_suppressed={row['suppressed_true_rows']:>2} "
            f"useful_true_suppressed={row['suppressed_useful_true_rows']:>2} "
            f"lost_distinct_gt={row['lost_distinct_gt_from_true_rows']:>2} "
            f"false_generated_removed={row['suppressed_false_generated_candidates']:>3} "
            f"false_kept={row['kept_false_rows']:>2}"
        )

    safe = [
        row
        for row in x4_only_sweeps
        if row["suppressed_useful_true_rows"] == 0
        and row["lost_distinct_gt_from_true_rows"] == 0
    ]
    print("\n=== zero-observed-GT-loss x4-only thresholds ===")
    for row in safe:
        print(json.dumps(row, ensure_ascii=False))

    result = {
        "schema_version": "issue372.probe_seed_competing_row_sweep.v1",
        "source_report": str(report_path.resolve()),
        "sweeps": sweeps,
        "x4_only_overlap_sweeps": x4_only_sweeps,
        "zero_observed_gt_loss_x4_only": safe,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args.report.resolve())
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nOUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
