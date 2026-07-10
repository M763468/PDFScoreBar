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

CURRENT_RUN = Path(
    "logs/issue244_full_regression/runs/production_default_full68"
)
CURRENT_EVAL = Path("logs/issue244_full_regression/detector_eval")
HISTORICAL_RUN = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
HISTORICAL_EVAL = HISTORICAL_RUN / "eval_detector"
MMR_SUMMARY = Path(
    "logs/issue244_full_regression/mmr_eval/aggregated_eval_summary.json"
)
MMR_LOG = Path("logs/issue244_full_regression/mmr_eval.log")
REPORT = Path("logs/issue244_full_regression/full68_regression_report.json")

EXPECTED_DETECTOR = {
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
    return [
        {field: row.get(field, "") for field in PAGE_METRIC_FIELDS}
        for row in rows
    ]


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


def main() -> int:
    current_detector = detector_summary(CURRENT_EVAL)
    historical_detector = detector_summary(HISTORICAL_EVAL)

    current_page_metrics = normalized_page_metrics(
        CURRENT_EVAL / "detector_page_metrics.csv"
    )
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
        "current_detector_matches_canonical_target": all(
            current_detector.get(key) == value
            for key, value in EXPECTED_DETECTOR.items()
        ),
        "historical_detector_matches_canonical_target": all(
            historical_detector.get(key) == value
            for key, value in EXPECTED_DETECTOR.items()
        ),
        "detector_page_metrics_match_historical": (
            current_page_metrics == historical_page_metrics
        ),
        "physical_measure_counts_match_historical": not numbering_mismatches,
        "mmr_matches_post_issue221_baseline": all(
            mmr_summary.get(key) == value for key, value in EXPECTED_MMR.items()
        ),
        "page033_one_bar_veto_present": veto_marker in mmr_log_text,
    }

    report = {
        "schema": "issue244.full68_regression.v1",
        "paths": {
            "current_run": str(CURRENT_RUN),
            "current_eval": str(CURRENT_EVAL),
            "historical_run": str(HISTORICAL_RUN),
            "historical_eval": str(HISTORICAL_EVAL),
            "mmr_summary": str(MMR_SUMMARY),
            "mmr_log": str(MMR_LOG),
        },
        "expected_detector": EXPECTED_DETECTOR,
        "current_detector": current_detector,
        "historical_detector": historical_detector,
        "expected_mmr": EXPECTED_MMR,
        "current_mmr": mmr_summary,
        "numbering_mismatches": numbering_mismatches,
        "checks": checks,
    }
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Full-68 regression checks")
    for name, passed in checks.items():
        print(f"  {name}: {passed}")
    print(f"Numbering mismatch pages: {sorted(numbering_mismatches)}")
    print(f"Report: {REPORT}")

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
