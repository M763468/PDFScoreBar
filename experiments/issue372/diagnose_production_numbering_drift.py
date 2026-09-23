#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ref_rows(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = report["variants"]["combined_late_raw_frozen_bands"]["per_page"]
    return {
        (str(row["score"]), str(row["page"])): row
        for row in rows
        if isinstance(row, Mapping)
    }


def fresh_rows(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    result = {}
    for score_summary in report["score_summaries"]:
        score = str(score_summary["score"])
        for page, row in score_summary["page_results"].items():
            result[(score, str(page))] = row
    return result


def measure_counts(logical: Mapping[str, Any]) -> list[int]:
    return [int(system["measure_count"]) for system in logical["systems"]]


def number_sequences(logical: Mapping[str, Any]) -> list[list[Any]]:
    return [list(system["numbers"]) for system in logical["systems"]]


def override_semantics(rows: Any) -> list[tuple[int, int, int]]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            result.append((int(row["system"]), int(row["measure"]), int(row["skip"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result)


def override_stats(rows: list[tuple[int, int, int]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "skip_sum": sum(skip for _, _, skip in rows),
        "max_skip": max((skip for _, _, skip in rows), default=0),
        "rows": [
            {"system": system, "measure": measure, "skip": skip}
            for system, measure, skip in rows
        ],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    fresh_report = load(args.production_report.resolve())
    reference_report = load(args.reference_replay.resolve())
    fresh = fresh_rows(fresh_report)
    reference = ref_rows(reference_report)
    rows = []
    first_drift: dict[str, dict[str, Any]] = {}

    for key in sorted(set(fresh) | set(reference)):
        score, page = key
        if key not in fresh or key not in reference:
            rows.append({"score": score, "page": page, "missing": True})
            continue

        left = reference[key]
        right = fresh[key]
        ref_counts = measure_counts(left["continued_logical"])
        new_counts = measure_counts(right["continued_logical"])
        ref_nums = number_sequences(left["continued_logical"])
        new_nums = number_sequences(right["continued_logical"])
        ref_mmr = override_semantics(left.get("mmr_overrides", []))
        new_mmr = override_semantics(right.get("mmr_overrides", []))
        start_delta = int(right["continued_start_number"]) - int(left["continued_start_number"])
        next_delta = int(right["continued_next_number"]) - int(left["continued_next_number"])

        row = {
            "score": score,
            "page": page,
            "topology_equal": ref_counts == new_counts,
            "number_values_equal": ref_nums == new_nums,
            "override_semantics_equal": ref_mmr == new_mmr,
            "reference_start": int(left["continued_start_number"]),
            "fresh_start": int(right["continued_start_number"]),
            "start_delta": start_delta,
            "reference_next": int(left["continued_next_number"]),
            "fresh_next": int(right["continued_next_number"]),
            "next_delta": next_delta,
            "reference_mmr": override_stats(ref_mmr),
            "fresh_mmr": override_stats(new_mmr),
        }
        rows.append(row)
        if (start_delta or next_delta) and score not in first_drift:
            first_drift[score] = row

    target = next(
        row for row in rows
        if row.get("score") == "Shostakovich-Sym5-Va"
        and row.get("page") == "page_021"
    )
    mmr_changed = [
        row for row in rows
        if not row.get("missing") and not row["override_semantics_equal"]
    ]
    topology_changed = [
        row for row in rows
        if not row.get("missing") and not row["topology_equal"]
    ]
    numbering_changed = [
        row for row in rows
        if not row.get("missing") and not row["number_values_equal"]
    ]

    result = {
        "schema_version": "issue372.production_numbering_drift_diagnosis.v1",
        "summary": {
            "page_count": len([row for row in rows if not row.get("missing")]),
            "topology_changed_page_count": len(topology_changed),
            "semantic_mmr_changed_page_count": len(mmr_changed),
            "number_value_changed_page_count": len(numbering_changed),
            "page021_topology_equal": target["topology_equal"],
            "page021_override_semantics_equal": target["override_semantics_equal"],
            "page021_start_delta": target["start_delta"],
            "page021_next_delta": target["next_delta"],
        },
        "first_continuation_drift_by_score": first_drift,
        "page021": target,
        "semantic_mmr_changed_pages": mmr_changed,
        "topology_changed_pages": topology_changed,
        "rows": rows,
    }

    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 production numbering drift diagnosis ===")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print("\n=== first continuation drift by score ===")
    for score, row in first_drift.items():
        print(
            f"{score}/{row['page']}: "
            f"start {row['reference_start']}->{row['fresh_start']} "
            f"(delta={row['start_delta']}), "
            f"next {row['reference_next']}->{row['fresh_next']} "
            f"(delta={row['next_delta']}), "
            f"mmr_equal={row['override_semantics_equal']}"
        )
        if not row["override_semantics_equal"]:
            print("  reference_mmr=", row["reference_mmr"])
            print("  fresh_mmr=", row["fresh_mmr"])

    print("\n=== page_021 ===")
    print(json.dumps(target, indent=2, ensure_ascii=False))

    print("\n=== semantic MMR changed pages ===")
    for row in mmr_changed:
        print(
            f"{row['score']}/{row['page']}: "
            f"reference={row['reference_mmr']} fresh={row['fresh_mmr']}"
        )
    print(f"\nOUTPUT={out}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--reference-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
