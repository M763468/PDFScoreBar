#!/usr/bin/env python3
"""Classify Issue #372 combined-vs-current numbering differences.

Retained-only. No inference or pipeline execution.

Reads:
- combined downstream replay report;
- prior fresh downstream replay report containing current_control / accepted_d27.

For every combined-vs-current number-value change, classify whether it is:
- the intended local topology repair on Shostakovich-Sym5-Va/page_021;
- continuation-only propagation caused by that repair;
- or an independent local/MMR change requiring investigation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _map_combined(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = report["variants"]["combined_late_raw_frozen_bands"]["per_page"]
    return {
        (str(row["score"]), str(row["page"])): row
        for row in rows
        if isinstance(row, Mapping)
    }


def _map_ref(report: Mapping[str, Any], label: str) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = report["variants"][label]["per_page"]
    return {
        (str(row["score"]), str(row["page"])): row
        for row in rows
        if isinstance(row, Mapping)
    }


def _measure_counts(logical: Mapping[str, Any]) -> list[int]:
    return [int(system["measure_count"]) for system in logical["systems"]]


def _numbers(logical: Mapping[str, Any]) -> list[list[Any]]:
    return [list(system["numbers"]) for system in logical["systems"]]


def _flatten_numbers(logical: Mapping[str, Any]) -> list[Any]:
    return [n for system in _numbers(logical) for n in system]


def _all_int_shift(left: list[Any], right: list[Any], shift: int) -> bool:
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if not isinstance(a, int) or not isinstance(b, int):
            return False
        if b != a + shift:
            return False
    return True


def _classify(
    current: Mapping[str, Any],
    combined: Mapping[str, Any],
) -> dict[str, Any]:
    local_current = current["local_logical"]
    local_combined = combined["local_logical"]
    cont_current = current["continued_logical"]
    cont_combined = combined["continued_logical"]

    local_structure_equal = (
        local_current["system_count"] == local_combined["system_count"]
        and _measure_counts(local_current) == _measure_counts(local_combined)
    )
    local_numbers_equal = _numbers(local_current) == _numbers(local_combined)
    mmr_equal = current["mmr_overrides"] == combined["mmr_overrides"]

    start_delta = (
        int(combined["continued_start_number"])
        - int(current["continued_start_number"])
    )
    next_delta = (
        int(combined["continued_next_number"])
        - int(current["continued_next_number"])
    )
    continued_structure_equal = (
        cont_current["system_count"] == cont_combined["system_count"]
        and _measure_counts(cont_current) == _measure_counts(cont_combined)
    )
    continued_numbers_shift_only = _all_int_shift(
        _flatten_numbers(cont_current),
        _flatten_numbers(cont_combined),
        start_delta,
    )

    continuation_only = (
        local_structure_equal
        and local_numbers_equal
        and mmr_equal
        and continued_structure_equal
        and continued_numbers_shift_only
        and next_delta == start_delta
    )

    return {
        "local_structure_equal": local_structure_equal,
        "local_numbers_equal": local_numbers_equal,
        "mmr_overrides_equal": mmr_equal,
        "continued_structure_equal": continued_structure_equal,
        "continued_start_delta": start_delta,
        "continued_next_delta": next_delta,
        "continued_numbers_shift_only": continued_numbers_shift_only,
        "continuation_only_propagation": continuation_only,
        "current": {
            "local_measure_counts": _measure_counts(local_current),
            "continued_measure_counts": _measure_counts(cont_current),
            "continued_start": current["continued_start_number"],
            "continued_next": current["continued_next_number"],
            "mmr_overrides": current["mmr_overrides"],
        },
        "combined": {
            "local_measure_counts": _measure_counts(local_combined),
            "continued_measure_counts": _measure_counts(cont_combined),
            "continued_start": combined["continued_start_number"],
            "continued_next": combined["continued_next_number"],
            "mmr_overrides": combined["mmr_overrides"],
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    combined_report = _load(args.combined_report.resolve())
    reference_report = _load(args.reference_replay.resolve())
    if not isinstance(combined_report, Mapping) or not isinstance(reference_report, Mapping):
        raise ValueError("reports must be JSON objects")

    combined = _map_combined(combined_report)
    current = _map_ref(reference_report, "current_control")
    d27 = _map_ref(reference_report, "accepted_d27")

    changed_rows = (
        combined_report["number_value_comparisons"]["combined_vs_current"]["changed_pages"]
    )
    changed_keys = [
        (str(row["score"]), str(row["page"]))
        for row in changed_rows
        if isinstance(row, Mapping)
    ]

    rows = []
    for key in changed_keys:
        row = {
            "score": key[0],
            "page": key[1],
            **_classify(current[key], combined[key]),
        }
        rows.append(row)

    page021 = ("Shostakovich-Sym5-Va", "page_021")
    page021_vs_d27 = {
        "local_logical_equal": combined[page021]["local_logical"] == d27[page021]["local_logical"],
        "continued_logical_equal": (
            combined[page021]["continued_logical"] == d27[page021]["continued_logical"]
        ),
        "continued_start_equal": (
            combined[page021]["continued_start_number"]
            == d27[page021]["continued_start_number"]
        ),
        "continued_next_equal": (
            combined[page021]["continued_next_number"]
            == d27[page021]["continued_next_number"]
        ),
        "mmr_overrides_equal": (
            combined[page021]["mmr_overrides"] == d27[page021]["mmr_overrides"]
        ),
    }

    non_page021 = [row for row in rows if (row["score"], row["page"]) != page021]
    result = {
        "schema_version": "issue372.combined_numbering_propagation.v1",
        "summary": {
            "changed_page_count": len(rows),
            "page021_matches_d27_all_blocking_fields": all(page021_vs_d27.values()),
            "non_page021_changed_count": len(non_page021),
            "non_page021_continuation_only_count": sum(
                row["continuation_only_propagation"] for row in non_page021
            ),
            "independent_non_page021_change_count": sum(
                not row["continuation_only_propagation"] for row in non_page021
            ),
        },
        "page021_vs_d27": page021_vs_d27,
        "changed_pages": rows,
    }

    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 combined numbering propagation ===")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print("\n=== page_021 vs D27 ===")
    print(json.dumps(page021_vs_d27, indent=2, ensure_ascii=False))
    print("\n=== combined vs current changed pages ===")
    for row in rows:
        print(
            f"{row['score']}/{row['page']} "
            f"local_structure_equal={row['local_structure_equal']} "
            f"local_numbers_equal={row['local_numbers_equal']} "
            f"mmr_equal={row['mmr_overrides_equal']} "
            f"start_delta={row['continued_start_delta']} "
            f"next_delta={row['continued_next_delta']} "
            f"continuation_only={row['continuation_only_propagation']}"
        )
        print(
            f"  current measures={row['current']['continued_measure_counts']} "
            f"start={row['current']['continued_start']} next={row['current']['continued_next']}"
        )
        print(
            f"  combined measures={row['combined']['continued_measure_counts']} "
            f"start={row['combined']['continued_start']} next={row['combined']['continued_next']}"
        )
    print(f"\nOUTPUT={out}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-report", type=Path, required=True)
    parser.add_argument("--reference-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
