#!/usr/bin/env python3
"""Compare greedy vs maximum-cardinality Stage E matching for Issue #284.

Read-only retained-artifact diagnostic. This does not change the accepted metric
contract; maximum matching is used only to determine whether current greedy FNs
represent missing one-to-one coverage or assignment-order competition.
This file is temporary and must be removed before PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import is_barline_match  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import SCORES  # noqa: E402
from tools.issue284.diagnose_stage_e_fn_regression import (  # noqa: E402
    RULE_NAME,
    VOV_THRESHOLD,
    XDIST_THRESHOLD,
    evaluate_run,
)


def is_match(pred: tuple[int, int, int, int], gt: tuple[int, int, int, int]) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name=RULE_NAME,
        vov_threshold=VOV_THRESHOLD,
        xdist_threshold=XDIST_THRESHOLD,
    )


def maximum_matching(
    predictions: list[tuple[int, int, int, int]],
    ground_truth: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    adjacency = [
        [gt_idx for gt_idx, gt in enumerate(ground_truth) if is_match(pred, gt)]
        for pred in predictions
    ]
    gt_to_pred: dict[int, int] = {}

    def augment(pred_idx: int, seen_gt: set[int]) -> bool:
        for gt_idx in adjacency[pred_idx]:
            if gt_idx in seen_gt:
                continue
            seen_gt.add(gt_idx)
            previous = gt_to_pred.get(gt_idx)
            if previous is None or augment(previous, seen_gt):
                gt_to_pred[gt_idx] = pred_idx
                return True
        return False

    for pred_idx in range(len(predictions)):
        augment(pred_idx, set())

    pred_to_gt = {pred_idx: gt_idx for gt_idx, pred_idx in gt_to_pred.items()}
    unmatched_gt = sorted(set(range(len(ground_truth))) - set(gt_to_pred))
    unmatched_pred = sorted(set(range(len(predictions))) - set(pred_to_gt))
    return {
        "tp": len(gt_to_pred),
        "fn": len(unmatched_gt),
        "unmatched_gt_indices": unmatched_gt,
        "unmatched_pred_indices": unmatched_pred,
        "gt_to_pred": gt_to_pred,
    }


def analyze(root: Path) -> dict[str, Any]:
    run = evaluate_run(root.resolve())
    totals = {
        "gt": 0,
        "pred": 0,
        "greedy_tp": 0,
        "greedy_fn": 0,
        "maximum_tp": 0,
        "maximum_fn": 0,
    }
    pages: list[dict[str, Any]] = []

    for score, page_list in SCORES.items():
        for page in page_list:
            data = run["_pages"][(score, page)]
            maximum = maximum_matching(data["pred"], data["gt"])
            greedy = data["matched"]
            greedy_fn = list(greedy.false_negative_indices)
            row = {
                "score": score,
                "page": page,
                "gt": len(data["gt"]),
                "pred": len(data["pred"]),
                "greedy_tp": len(greedy.matches),
                "greedy_fn": len(greedy_fn),
                "greedy_fn_indices": greedy_fn,
                "maximum_tp": maximum["tp"],
                "maximum_fn": maximum["fn"],
                "maximum_fn_indices": maximum["unmatched_gt_indices"],
                "greedy_recoverable_fn_indices": sorted(
                    set(greedy_fn) - set(maximum["unmatched_gt_indices"])
                ),
            }
            if row["greedy_fn"] or row["maximum_fn"] or row["greedy_tp"] != row["maximum_tp"]:
                pages.append(row)
            for key in totals:
                totals[key] += int(row[key])

    return {
        "root": str(root.resolve()),
        "totals": totals,
        "interesting_pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-root", type=Path, required=True)
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue284/issue284_stage_e_maximum_matching.json"),
    )
    args = parser.parse_args()

    accepted = analyze(args.accepted_root)
    current = analyze(args.current_root)
    payload = {
        "schema_version": "issue284.stage_e_maximum_matching.v1",
        "read_only": True,
        "note": "Maximum matching is diagnostic only; accepted metrics remain greedy center-anchor.",
        "accepted": accepted,
        "current": current,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "accepted_totals": accepted["totals"],
                "current_totals": current["totals"],
                "accepted_interesting_pages": accepted["interesting_pages"],
                "current_interesting_pages": current["interesting_pages"],
                "output": str(args.output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
