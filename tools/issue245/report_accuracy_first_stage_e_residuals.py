#!/usr/bin/env python3
"""Report residual FP/FN details for the Issue #245 accuracy-first Stage E run.

This reads saved scored/candidate artifacts only. It does not rerun detector inference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.common.barline_evaluation import greedy_barline_match
from tools.issue120.eval_full68_from_intermediates import (
    SCORES,
    boxes_from_candidates,
    boxes_from_gt,
    boxes_from_scored,
    find_page_file,
    has_candidate_for_gt,
    load_json,
)


def build_report(
    *,
    mixed_results_root: Path,
    historical_results_root: Path,
    gt_root: Path,
    score_threshold: float,
    rule_name: str,
    vov_threshold: float,
    xdist_threshold: float,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    totals = {
        "mixed_fp": 0,
        "mixed_fn": 0,
        "mixed_fn_det": 0,
        "mixed_fn_cnn": 0,
        "mixed_fn_also_historical_fn": 0,
        "mixed_fn_historical_matched": 0,
    }

    for score, page_names in SCORES.items():
        for page in page_names:
            record = type("Record", (), {"score": score, "page": page})()
            gt_path = gt_root / score / page / "boxes_sorted.json"
            mixed_scored_path = find_page_file(
                mixed_results_root, record, "pipeline2_no_peak_scored.json"
            )
            mixed_candidates_path = find_page_file(
                mixed_results_root, record, "pipeline2_no_peak_candidates.json"
            )
            historical_scored_path = find_page_file(
                historical_results_root, record, "pipeline2_no_peak_scored.json"
            )
            historical_candidates_path = find_page_file(
                historical_results_root, record, "pipeline2_no_peak_candidates.json"
            )

            required = {
                "gt": gt_path,
                "mixed_scored": mixed_scored_path,
                "mixed_candidates": mixed_candidates_path,
                "historical_scored": historical_scored_path,
                "historical_candidates": historical_candidates_path,
            }
            missing = [name for name, path in required.items() if path is None or not path.exists()]
            if missing:
                raise FileNotFoundError(
                    f"Missing inputs for {score}/{page}: {', '.join(missing)}"
                )

            gts = boxes_from_gt(load_json(gt_path))
            mixed_preds = boxes_from_scored(
                load_json(mixed_scored_path), score_threshold=score_threshold
            )
            mixed_candidates = boxes_from_candidates(load_json(mixed_candidates_path))
            historical_preds = boxes_from_scored(
                load_json(historical_scored_path), score_threshold=score_threshold
            )
            historical_candidates = boxes_from_candidates(load_json(historical_candidates_path))

            mixed_match = greedy_barline_match(
                mixed_preds,
                gts,
                rule_name=rule_name,
                vov_threshold=vov_threshold,
                xdist_threshold=xdist_threshold,
            )
            historical_match = greedy_barline_match(
                historical_preds,
                gts,
                rule_name=rule_name,
                vov_threshold=vov_threshold,
                xdist_threshold=xdist_threshold,
            )
            historical_fn_indices = set(historical_match.false_negative_indices)

            false_negatives: list[dict[str, Any]] = []
            for gt_index in mixed_match.false_negative_indices:
                gt = gts[gt_index]
                mixed_candidate_present = has_candidate_for_gt(
                    mixed_candidates,
                    gt,
                    rule_name=rule_name,
                    vov_threshold=vov_threshold,
                    xdist_threshold=xdist_threshold,
                )
                historical_candidate_present = has_candidate_for_gt(
                    historical_candidates,
                    gt,
                    rule_name=rule_name,
                    vov_threshold=vov_threshold,
                    xdist_threshold=xdist_threshold,
                )
                historical_missed = gt_index in historical_fn_indices
                false_negatives.append(
                    {
                        "gt_index": gt_index,
                        "gt_bbox": list(gt),
                        "mixed_stage": "cnn" if mixed_candidate_present else "detector",
                        "mixed_candidate_present": mixed_candidate_present,
                        "historical_missed_same_gt": historical_missed,
                        "historical_candidate_present": historical_candidate_present,
                    }
                )
                totals["mixed_fn"] += 1
                totals["mixed_fn_cnn" if mixed_candidate_present else "mixed_fn_det"] += 1
                totals[
                    "mixed_fn_also_historical_fn"
                    if historical_missed
                    else "mixed_fn_historical_matched"
                ] += 1

            false_positives = [
                {"pred_index": index, "pred_bbox": list(mixed_preds[index])}
                for index in mixed_match.false_positive_indices
            ]
            totals["mixed_fp"] += len(false_positives)

            if false_negatives or false_positives:
                pages.append(
                    {
                        "score": score,
                        "page": page,
                        "mixed_scored_path": str(mixed_scored_path),
                        "mixed_candidates_path": str(mixed_candidates_path),
                        "historical_scored_path": str(historical_scored_path),
                        "historical_candidates_path": str(historical_candidates_path),
                        "gt_path": str(gt_path),
                        "mixed_false_negatives": false_negatives,
                        "mixed_false_positives": false_positives,
                        "historical_fn_count": len(historical_match.false_negative_indices),
                        "historical_fp_count": len(historical_match.false_positive_indices),
                    }
                )

    return {
        "schema_version": "issue245.accuracy_first_stage_e_residuals.v1",
        "mixed_results_root": str(mixed_results_root),
        "historical_results_root": str(historical_results_root),
        "gt_root": str(gt_root),
        "score_threshold": score_threshold,
        "rule_name": rule_name,
        "vov_threshold": vov_threshold,
        "xdist_threshold": xdist_threshold,
        "totals": totals,
        "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mixed-results-root", type=Path, required=True)
    parser.add_argument(
        "--historical-results-root",
        type=Path,
        default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"),
    )
    parser.add_argument(
        "--gt-root", type=Path, default=Path("data/evaluation2/annotations")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    args = parser.parse_args()

    report = build_report(
        mixed_results_root=args.mixed_results_root,
        historical_results_root=args.historical_results_root,
        gt_root=args.gt_root,
        score_threshold=args.score_threshold,
        rule_name=args.rule_name,
        vov_threshold=args.vov_threshold,
        xdist_threshold=args.xdist_threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    totals = report["totals"]
    print(
        "Residuals: "
        f"FP={totals['mixed_fp']} FN={totals['mixed_fn']} "
        f"FN_det={totals['mixed_fn_det']} FN_cnn={totals['mixed_fn_cnn']}"
    )
    print(
        "Historical overlap: "
        f"same_historical_fn={totals['mixed_fn_also_historical_fn']} "
        f"historical_matched={totals['mixed_fn_historical_matched']}"
    )
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
