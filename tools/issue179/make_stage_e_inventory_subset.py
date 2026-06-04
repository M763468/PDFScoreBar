#!/usr/bin/env python3
"""Create a small Stage E inventory subset for Issue #179 timing comparisons."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def _excluded_keys(exclude_obj: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in exclude_obj.get("excluded_pages", []):
        if isinstance(item, dict) and "score" in item and "page" in item:
            keys.add((str(item["score"]), str(item["page"])))
    return keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output-inventory", type=Path, required=True)
    parser.add_argument("--output-exclude", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Zero-based index among non-excluded records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count must be positive")
    if args.start_index < 0:
        raise ValueError("--start-index must be >= 0")

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    exclude_obj = json.loads(args.exclude.read_text(encoding="utf-8"))

    records = inventory.get("records")
    if not isinstance(records, list):
        raise ValueError("Inventory must contain a list field named 'records'.")

    excluded = _excluded_keys(exclude_obj)
    eligible: list[dict[str, Any]] = []
    skipped_excluded: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = (str(rec.get("score")), str(rec.get("page")))
        if key in excluded:
            skipped_excluded.append({"score": key[0], "page": key[1]})
            continue
        eligible.append(rec)

    selected = eligible[args.start_index : args.start_index + args.count]
    if len(selected) != args.count:
        raise ValueError(
            f"Requested {args.count} records from start-index {args.start_index}, "
            f"but only {len(selected)} eligible records are available."
        )

    subset_inventory = copy.deepcopy(inventory)
    subset_inventory["records"] = selected
    subset_inventory["issue179_subset"] = {
        "source_inventory": str(args.inventory),
        "source_exclude": str(args.exclude),
        "count": args.count,
        "start_index": args.start_index,
    }

    subset_exclude = copy.deepcopy(exclude_obj)
    subset_exclude["excluded_pages"] = []
    subset_exclude["issue179_subset"] = {
        "source_exclude": str(args.exclude),
        "reason": "Subset was selected from non-excluded records only.",
    }

    args.output_inventory.parent.mkdir(parents=True, exist_ok=True)
    args.output_exclude.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)

    args.output_inventory.write_text(
        json.dumps(subset_inventory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    args.output_exclude.write_text(
        json.dumps(subset_exclude, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    args.summary_out.write_text(
        json.dumps(
            {
                "schema_version": "tools.issue179.stage_e_inventory_subset.v1",
                "source_inventory": str(args.inventory),
                "source_exclude": str(args.exclude),
                "output_inventory": str(args.output_inventory),
                "output_exclude": str(args.output_exclude),
                "requested_count": args.count,
                "start_index": args.start_index,
                "selected_count": len(selected),
                "selected_pages": [
                    {"score": str(rec.get("score")), "page": str(rec.get("page"))}
                    for rec in selected
                ],
                "source_excluded_count": len(skipped_excluded),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Wrote subset inventory: {args.output_inventory}")
    print(f"Wrote subset exclude:   {args.output_exclude}")
    print(f"Wrote subset summary:   {args.summary_out}")


if __name__ == "__main__":
    main()
