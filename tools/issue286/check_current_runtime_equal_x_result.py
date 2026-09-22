#!/usr/bin/env python3
"""Evaluate Issue #286 current-runtime equal-x acceptance from a retained audit JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_PAGE_COUNT = 68
EXPECTED_TIE_PAGE_COUNT = 16
EXPECTED_TIE_GROUP_COUNT = 36
EXPECTED_SELECTORS = {
    "staff_order_first",
    "staff_order_last",
    "topmost",
    "bottommost",
    "narrower",
    "wider",
    "tallest",
    "shortest",
}


def evaluate_acceptance(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    summary = data.get("summary") or {}
    failures: list[str] = []

    if data.get("runtime_contract_drift"):
        failures.append(f"runtime_contract_drift={data['runtime_contract_drift']!r}")
    if data.get("contract_drift"):
        failures.append(f"contract_drift={data['contract_drift']!r}")

    if summary.get("page_count") != EXPECTED_PAGE_COUNT:
        failures.append(f"page_count={summary.get('page_count')!r}")
    if summary.get("equal_x_tie_page_count") != EXPECTED_TIE_PAGE_COUNT:
        failures.append(
            f"equal_x_tie_page_count={summary.get('equal_x_tie_page_count')!r}"
        )
    if summary.get("equal_x_tie_group_count") != EXPECTED_TIE_GROUP_COUNT:
        failures.append(
            f"equal_x_tie_group_count={summary.get('equal_x_tie_group_count')!r}"
        )

    selectors = summary.get("selectors") or {}
    missing_selectors = sorted(EXPECTED_SELECTORS - set(selectors))
    if missing_selectors:
        failures.append(f"missing selector summaries: {missing_selectors!r}")

    wider = selectors.get("wider") or {}
    wider_logical = wider.get("logical_changed_from_current_replay_pages") or []
    wider_geometry = wider.get("geometry_changed_from_current_replay_pages") or []

    if wider_logical:
        failures.append(
            f"wider changed logical numbering/topology: {wider_logical!r}"
        )
    if wider_geometry:
        failures.append(
            "production replay does not match wider-first geometry: "
            f"{wider_geometry!r}"
        )

    selector_logical_changes: dict[str, list[str]] = {}
    for name, selector in selectors.items():
        changed = selector.get("logical_changed_from_current_replay_pages") or []
        selector_logical_changes[name] = list(changed)
        if changed:
            failures.append(f"{name} changed logical numbering/topology: {changed!r}")

    wider_decision_count = 0
    for page_name, page_result in (data.get("pages") or {}).items():
        decisions = (
            ((page_result.get("selectors") or {}).get("wider") or {}).get("decisions")
            or []
        )
        for decision in decisions:
            boxes = decision.get("boxes") or []
            selected = decision.get("selected")
            if not boxes or selected is None:
                continue
            wider_decision_count += 1
            max_width = max(box[2] - box[0] for box in boxes)
            selected_width = selected[2] - selected[0]
            if selected_width != max_width:
                failures.append(
                    f"{page_name} x1={decision.get('x1')} did not choose a widest "
                    f"candidate: selected={selected!r} boxes={boxes!r}"
                )

    if wider_decision_count != EXPECTED_TIE_GROUP_COUNT:
        failures.append(
            f"wider_decision_count={wider_decision_count!r}; "
            f"expected={EXPECTED_TIE_GROUP_COUNT}"
        )

    page_013 = (data.get("pages") or {}).get("Shostakovich-Sym5-Va/page_013") or {}
    page_013_decisions = (
        ((page_013.get("selectors") or {}).get("wider") or {}).get("decisions")
        or []
    )
    page_013_x1788 = [
        decision
        for decision in page_013_decisions
        if decision.get("x1") == 1788
    ]

    compact = {
        "source_commit": data.get("source_commit"),
        "page_count": summary.get("page_count"),
        "equal_x_tie_page_count": summary.get("equal_x_tie_page_count"),
        "equal_x_tie_group_count": summary.get("equal_x_tie_group_count"),
        "wider_logical_changed": wider_logical,
        "wider_geometry_changed": wider_geometry,
        "selector_logical_changes": selector_logical_changes,
        "wider_decision_count": wider_decision_count,
        "page_013_x1788_current_wider_decision": page_013_x1788,
        "acceptance": "PASS" if not failures else "FAIL",
    }
    return compact, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    data = json.loads(args.result.read_text(encoding="utf-8"))
    compact, failures = evaluate_acceptance(data)
    output = json.dumps(compact, indent=2, ensure_ascii=False)
    print(output)

    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(output + "\n", encoding="utf-8")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 31

    print("ISSUE286_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
