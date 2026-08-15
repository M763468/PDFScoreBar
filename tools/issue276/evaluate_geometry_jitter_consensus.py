#!/usr/bin/env python3
"""Bounded, diagnostic-only geometry-jitter consensus evaluation for Issue #276."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "logs/issue276_final_trace/issue276_mmr_ocr_geometry_trace.json"
AUDIT = ROOT / "logs/issue274_positive_geometry_audit/issue274_positive_geometry_audit.json"
OUT = ROOT / "logs/issue276_geometry_jitter_consensus/issue276_geometry_jitter_consensus.json"


def strict_majority(values: Iterable[int | None], required: int) -> int | None:
    counts = Counter(value for value in values if value is not None and value >= 2)
    if not counts:
        return None
    value, count = counts.most_common(1)[0]
    return value if count >= required else None


def project(baseline: int | None, vote: int | None, mode: str) -> int | None:
    if vote is not None:
        return vote
    return baseline if mode == "KEEP" else None


def _index(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {row["name"]: row for row in rows}


def views(summary: Mapping[str, Any], name: str) -> list[int | None]:
    horizontal = _index(summary["horizontal_measure_driven"])
    vertical = _index(summary["vertical_staff_driven"])
    suffix = {"J1": ("-1", "+1"), "J2": ("-2", "+2"), "J12": ("-2", "-1", "+1", "+2")}[name]
    selected = [horizontal["baseline"]]
    selected += [horizontal[f"shift_x{x}"] for x in suffix]
    selected += [vertical[f"staff_shift_y{x}"] for x in suffix]
    return [row["found_num"] for row in selected]


def inventory(audit: Mapping[str, Any]) -> dict[str, Any]:
    rows = audit["production_path_traces"]
    primary = [
        next((x for x in row["production_path_trace"] if x["view"] == "primary"), None)
        for row in rows
    ]
    primary = [x for x in primary if x]
    scores = [x["score"] for x in primary]
    variants = [x["debug"].rsplit("variant=", 1)[-1] for x in primary]
    return {
        "positive_cases": len(rows),
        "score_thresholds": {str(t): sum(score <= t for score in scores) for t in (0, 5, 10, 20)},
        "variant_disagreement_proxy": sum(
            len(
                {x["found_num"] for x in row["production_path_trace"] if x["found_num"] is not None}
            )
            > 1
            for row in rows
        ),
        "variant_names": Counter(variants),
    }


def run(trace_path: Path = TRACE, audit_path: Path = AUDIT, output: Path = OUT) -> Path:
    trace, audit = json.loads(trace_path.read_text()), json.loads(audit_path.read_text())
    cases = {}
    for page in ("page_025", "page_055"):
        baseline = trace["cases"][page]["reuse_geometry"]["final"]["found_num"]
        summary = trace["perturbation_summary"][page]
        plans = {}
        for name, need in (("J1", 3), ("J2", 3), ("J12", 5)):
            numbers = views(summary, name)
            majority = strict_majority(numbers, need)
            plans[name] = {
                "views": numbers,
                "strict_majority": majority,
                "KEEP": project(baseline, majority, "KEEP"),
                "REJECT": project(baseline, majority, "REJECT"),
                "ambiguous": majority is None,
            }
        cases[page] = {"baseline": baseline, "plans": plans}
    payload = {
        "schema_version": "issue276.geometry_jitter_consensus.v1",
        "scope": "diagnostic-only positive-key replacement; no new-measure discovery, no production modification, CNN probability reused by the source trace",
        "baseline_inventory": inventory(audit),
        "cases": cases,
        "runtime": {
            "additional_rapidocr_calls": 0,
            "cnn_calls": 0,
            "source_trace_rapidocr_calls": trace["runtime"]["rapidocr_calls"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    print(run(output=args.output))
