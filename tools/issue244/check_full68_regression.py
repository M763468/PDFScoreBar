#!/usr/bin/env python3
"""Compare the Issue #244 full-68 run with retained historical baselines.

Temporary acceptance helper. Delete before the final PR after the evidence has
been recorded in the issue/PR.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

CURRENT_RUN = Path("logs/issue244_full_regression/runs/production_default_full68")
CURRENT_EVAL = Path("logs/issue244_full_regression/detector_eval")
HISTORICAL_RUN = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
HISTORICAL_EVAL = HISTORICAL_RUN / "eval_detector"
MMR_SUMMARY = Path("logs/issue244_full_regression/mmr_eval/aggregated_eval_summary.json")
MMR_LOG = Path("logs/issue244_full_regression/mmr_eval.log")
REPORT = Path("logs/issue244_full_regression/full68_regression_report.json")

# Historical Stage E result before PR #203 removed one false GT barline.
HISTORICAL_PRE_GT_CORRECTION_TARGET = {
    "page_count": 68,
    "expected_page_count": 68,
    "gt": 3581,
    "pred": 3600,
    "tp": 3580,
    "fp": 0,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
    "precision": 1.0,
    "recall": 0.9997207483943032,
}

# The same retained Stage E detector artifact evaluated against current GT.
# The single page_060 FP is a known residual tracked by Issue #202; Issue #244
# must not hide it or misclassify the intentional GT correction as route drift.
CURRENT_GT_HISTORICAL_BASELINE = {
    "page_count": 68,
    "expected_page_count": 68,
    "gt": 3580,
    "pred": 3600,
    "tp": 3579,
    "fp": 1,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
}

EXPECTED_MMR = {
    "total_pages": 68,
    "total_base_measures": 3325,
    "total_expected": 182,
    "total_detected": 179,
    "matched_tp": 173,
    "missed_fn": 3,
    "skip_mismatch": 6,
    "unexpected_fp": 0,
}
PAGE_METRIC_FIELDS = (
    "score",
    "page",
    "gt",
    "pred",
    "candidate_count",
    "tp",
    "fp",
    "fn",
    "fn_det",
    "fn_cnn",
    "precision",
    "recall",
)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def detector_summary(eval_root: Path) -> dict[str, Any]:
    payload = load_json(eval_root / "evaluation_contract.json")
    summary = payload.get("detector_summary")
    if not isinstance(summary, dict):
        raise ValueError(f"No detector_summary in {eval_root}")
    return summary


def normalized_page_metrics(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [{field: row.get(field, "") for field in PAGE_METRIC_FIELDS} for row in rows]


def numbering_signature(run_root: Path) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index in range(1, 69):
        page_id = f"page_{index:03d}"
        path = run_root / "intermediate" / page_id / "numbering_base.json"
        payload = load_json(path)
        pages = payload.get("pages", [])
        if not isinstance(pages, list) or len(pages) != 1:
            raise ValueError(f"Expected one page in {path}")
        systems = pages[0].get("systems", [])
        if not isinstance(systems, list):
            raise ValueError(f"Expected systems in {path}")
        result[page_id] = [
            len(system.get("measures", []))
            if isinstance(system, dict) and isinstance(system.get("measures"), list)
            else 0
            for system in systems
        ]
    return result


def mismatched_pages(
    current: dict[str, list[int]],
    historical: dict[str, list[int]],
) -> dict[str, dict[str, list[int] | None]]:
    mismatches: dict[str, dict[str, list[int] | None]] = {}
    for page_id in sorted(set(current) | set(historical)):
        current_value = current.get(page_id)
        historical_value = historical.get(page_id)
        if current_value != historical_value:
            mismatches[page_id] = {
                "current": current_value,
                "historical": historical_value,
            }
    return mismatches


def matches_expected(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def summary_differences(
    current: dict[str, Any],
    historical: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    differences: dict[str, dict[str, Any]] = {}
    for key in sorted(set(current) | set(historical)):
        current_value = current.get(key)
        historical_value = historical.get(key)
        if current_value != historical_value:
            differences[key] = {
                "current": current_value,
                "historical": historical_value,
            }
    return differences


def main() -> int:
    current_detector = detector_summary(CURRENT_EVAL)
    historical_detector = detector_summary(HISTORICAL_EVAL)
    detector_differences = summary_differences(current_detector, historical_detector)

    current_page_metrics = normalized_page_metrics(CURRENT_EVAL / "detector_page_metrics.csv")
    historical_page_metrics = normalized_page_metrics(
        HISTORICAL_EVAL / "detector_page_metrics.csv"
    )

    current_numbering = numbering_signature(CURRENT_RUN)
    historical_numbering = numbering_signature(HISTORICAL_RUN)
    numbering_mismatches = mismatched_pages(current_numbering, historical_numbering)

    mmr_payload = load_json(MMR_SUMMARY)
    mmr_summary = mmr_payload.get("summary")
    if not isinstance(mmr_summary, dict):
        raise ValueError(f"No summary in {MMR_SUMMARY}")

    veto_marker = "[VETO] P33 S0 M1:"
    mmr_log_text = MMR_LOG.read_text(encoding="utf-8", errors="replace")

    checks = {
        "historical_detector_matches_current_gt_baseline": matches_expected(
            historical_detector,
            CURRENT_GT_HISTORICAL_BASELINE,
        ),
        "current_detector_matches_current_gt_baseline": matches_expected(
            current_detector,
            CURRENT_GT_HISTORICAL_BASELINE,
        ),
        "current_detector_summary_matches_historical": not detector_differences,
        "detector_page_metrics_match_historical": (
            current_page_metrics == historical_page_metrics
        ),
        "physical_measure_counts_match_historical": not numbering_mismatches,
        "mmr_matches_post_issue221_baseline": matches_expected(
            mmr_summary,
            EXPECTED_MMR,
        ),
        "page033_one_bar_veto_present": veto_marker in mmr_log_text,
    }

    report = {
        "schema": "issue244.full68_regression.v2",
        "baseline_interpretation": {
            "historical_pre_gt_correction_target": (
                "Issue #120 / Stage E result before PR #203 corrected page_060 GT"
            ),
            "current_gt_historical_baseline": (
                "The retained Stage E artifact re-evaluated against current GT"
            ),
            "known_current_gt_residual": {
                "issue": 202,
                "page_id": "page_060",
                "classification": "false_positive",
                "note": (
                    "The FP is expected for the retained/current detector model after the "
                    "intentional GT correction and is not introduced by Issue #244."
                ),
            },
        },
        "paths": {
            "current_run": str(CURRENT_RUN),
            "current_eval": str(CURRENT_EVAL),
            "historical_run": str(HISTORICAL_RUN),
            "historical_eval": str(HISTORICAL_EVAL),
            "mmr_summary": str(MMR_SUMMARY),
            "mmr_log": str(MMR_LOG),
        },
        "historical_pre_gt_correction_target": HISTORICAL_PRE_GT_CORRECTION_TARGET,
        "current_gt_historical_baseline": CURRENT_GT_HISTORICAL_BASELINE,
        "current_detector": current_detector,
        "historical_detector_re_evaluated_with_current_gt": historical_detector,
        "detector_summary_differences": detector_differences,
        "expected_mmr": EXPECTED_MMR,
        "current_mmr": mmr_summary,
        "numbering_mismatches": numbering_mismatches,
        "checks": checks,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Full-68 regression checks")
    for name, passed in checks.items():
        print(f"  {name}: {passed}")
    print(f"Detector summary differences: {sorted(detector_differences)}")
    print(f"Numbering mismatch pages: {sorted(numbering_mismatches)}")
    print(f"Report: {REPORT}")

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
