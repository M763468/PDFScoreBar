#!/usr/bin/env python3
"""Reclassify Issue #372 fresh downstream replay by user-visible numbering values.

The original replay intentionally treated empty-system accounting as a logical
difference. For #372 acceptance, the primary user-visible contract is narrower:

- serialized measure-number sequence;
- per-system physical measure counts;
- score-continuation start/next state;
- MMR skip overrides.

Empty-system bookkeeping and measure bbox geometry remain diagnostics, but do
not fail the numbering-value gate by themselves.

This is retained-only and runs no inference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _page_map(report: Mapping[str, Any], label: str) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = report["variants"][label]["per_page"]
    return {
        (str(row["score"]), str(row["page"])): row
        for row in rows
        if isinstance(row, Mapping)
    }


def _number_value_signature(row: Mapping[str, Any]) -> dict[str, Any]:
    local = row["local_logical"]
    continued = row["continued_logical"]
    return {
        "local_system_count": local["system_count"],
        "local_system_measure_counts": [
            system["measure_count"] for system in local["systems"]
        ],
        "local_number_sequences": [
            system["numbers"] for system in local["systems"]
        ],
        "continued_system_count": continued["system_count"],
        "continued_system_measure_counts": [
            system["measure_count"] for system in continued["systems"]
        ],
        "continued_number_sequences": [
            system["numbers"] for system in continued["systems"]
        ],
        "continued_start_number": row["continued_start_number"],
        "continued_next_number": row["continued_next_number"],
        "mmr_overrides": row["mmr_overrides"],
    }


def compare_number_values(
    left: Mapping[tuple[str, str], Mapping[str, Any]],
    right: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    keys = sorted(set(left) | set(right))
    changed: list[dict[str, Any]] = []
    exact = 0
    for key in keys:
        if key not in left or key not in right:
            changed.append({
                "score": key[0],
                "page": key[1],
                "reason": "missing_variant_page",
            })
            continue
        left_sig = _number_value_signature(left[key])
        right_sig = _number_value_signature(right[key])
        if left_sig == right_sig:
            exact += 1
            continue
        changed.append({
            "score": key[0],
            "page": key[1],
            "left": left_sig,
            "right": right_sig,
        })
    return {
        "number_value_match": not changed,
        "changed_page_count": len(changed),
        "exact_page_count": exact,
        "changed_pages": changed,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source.resolve()
    output = args.output.resolve()
    report = _load(source)
    if not isinstance(report, Mapping):
        raise ValueError("source report must be a JSON object")

    current = _page_map(report, "current_control")
    late = _page_map(report, "late_raw_x4")
    d27 = _page_map(report, "accepted_d27")

    late_vs_current = compare_number_values(current, late)
    late_vs_d27 = compare_number_values(d27, late)

    double_pages = [
        ("Sibelius-Violin_Concerto-Viola", "page_001"),
        ("Sibelius-Violin_Concerto-Viola", "page_003"),
    ]
    double_rows = []
    for key in double_pages:
        left = _number_value_signature(d27[key])
        right = _number_value_signature(late[key])
        double_rows.append({
            "score": key[0],
            "page": key[1],
            "number_value_match": left == right,
            "d27": left,
            "late_raw_x4": right,
        })

    result = {
        "schema_version": "issue372.number_value_reassessment.v1",
        "source_report": str(source),
        "acceptance_contract": {
            "primary_reference": "current maintained-HOMR production downstream",
            "blocking_fields": [
                "system count",
                "per-system physical measure count",
                "serialized measure-number sequence",
                "continued start/next number state",
                "MMR skip overrides",
            ],
            "diagnostic_only_fields": [
                "empty_system_count",
                "measure bbox geometry",
            ],
            "absolute_correctness_note": (
                "This gate proves #372 does not change current production numbering "
                "values. It does not claim that pre-existing #294 MMR residuals are "
                "absolutely correct."
            ),
        },
        "late_vs_current_number_values": late_vs_current,
        "late_vs_d27_number_values": late_vs_d27,
        "double_bar_pages": double_rows,
        "issue372_numbering_non_regression_pass": late_vs_current["number_value_match"],
        "double_bar_numbering_nonblocking": all(
            row["number_value_match"] for row in double_rows
        ),
    }
    _write(output, result)

    print("=== Issue #372 numbering-value reassessment ===")
    print(
        "late_vs_current=",
        late_vs_current["number_value_match"],
        "changed_pages=",
        late_vs_current["changed_page_count"],
    )
    print(
        "late_vs_d27=",
        late_vs_d27["number_value_match"],
        "changed_pages=",
        late_vs_d27["changed_page_count"],
    )
    print(
        "double_bar_numbering_nonblocking=",
        result["double_bar_numbering_nonblocking"],
    )
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
