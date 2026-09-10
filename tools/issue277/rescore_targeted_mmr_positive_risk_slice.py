#!/usr/bin/env python3
"""Classify Issue #277 retained-positive changes against the accepted #264 GT rebase.

This evaluator performs no inference.  It consumes a completed retained-positive
risk-slice report and the canonical accepted Issue #264 geometry-rebased score
report.  The latter supplies the physical/rebased expected key+skip contract, so
J2 mismatches that become correct are not confused with regressions merely because
they differ from the current baseline output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ACCEPTED_REBASE_SHA256 = "83bbe96b34fb9357c8c9ebaf29a1cce48296040306650091555a2e4ffad12471"
EXPECTED_POSITIVE_RECORDS = 175
EXPECTED_BASELINE_EXACT = 169
EXPECTED_BASELINE_MISMATCH = 6
EXPECTED_TOTAL_GT = 177
EXPECTED_BASELINE_FULL_FN = 2


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_index(report: Mapping[str, Any]) -> dict[tuple[int, int, int], int]:
    index: dict[tuple[int, int, int], int] = {}
    for page in report.get("pages", []):
        scoring = page.get("scoring", {})
        rows: list[tuple[Mapping[str, Any], str]] = []
        rows.extend((row, "skip") for row in scoring.get("matched", []))
        rows.extend((row, "expected_skip") for row in scoring.get("missed", []))
        rows.extend((row, "expected_skip") for row in scoring.get("skip_mismatch", []))
        for row, field in rows:
            key = tuple(int(value) for value in row["key"])
            skip = int(row[field])
            previous = index.get(key)
            if previous is not None and previous != skip:
                raise RuntimeError(f"Conflicting accepted expectation for {key}: {previous} vs {skip}")
            index[key] = skip
    return index


def _one_skip(rows: Sequence[Mapping[str, Any]]) -> int | None:
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError(f"Expected at most one sliced-measure override, got {len(rows)}")
    return int(rows[0].get("skip") or 0)


def result_state(actual_skip: int | None, expected_skip: int) -> str:
    if actual_skip is None:
        return "absent"
    return "exact" if int(actual_skip) == int(expected_skip) else "mismatch"


def classify_change(baseline_state: str, candidate_state: str, changed_value: bool) -> str:
    if baseline_state == "exact" and candidate_state != "exact":
        return "regression"
    if baseline_state != "exact" and candidate_state == "exact":
        return "improvement"
    if not changed_value:
        return "unchanged"
    return "changed_nonexact"


def run(risk_path: Path, accepted_path: Path, output_path: Path) -> dict[str, Any]:
    risk = _load_json(risk_path)
    accepted = _load_json(accepted_path)
    if not isinstance(risk, Mapping) or risk.get("status") != "completed":
        raise ValueError("Risk-slice report is not completed")
    if not isinstance(accepted, Mapping) or accepted.get("status") != "passed":
        raise ValueError("Accepted Issue #264 rebase report is not passed")

    accepted_sha = _sha256(accepted_path)
    if accepted_sha != ACCEPTED_REBASE_SHA256:
        raise RuntimeError(
            f"Accepted rebase fingerprint mismatch: {accepted_sha} != {ACCEPTED_REBASE_SHA256}"
        )
    accepted_summary = accepted.get("geometry_rebased_summary", {})
    if int(accepted_summary.get("expected", -1)) != EXPECTED_TOTAL_GT:
        raise RuntimeError("Accepted rebase expected-event count is not canonical 177")

    expected = _expected_index(accepted)
    records = [
        row for row in risk.get("records", [])
        if isinstance(row, Mapping) and row.get("kind") == "retained_positive"
    ]
    if len(records) != EXPECTED_POSITIVE_RECORDS:
        raise RuntimeError(f"Expected 175 retained positives, got {len(records)}")

    state_counts: dict[str, Counter[str]] = {
        "baseline": Counter(),
        "candidate": Counter(),
    }
    changes: list[dict[str, Any]] = []
    unmapped: list[list[int]] = []
    for row in records:
        key = tuple(int(value) for value in row["key"])
        expected_skip = expected.get(key)
        if expected_skip is None:
            unmapped.append(list(key))
            continue
        baseline_skip = _one_skip(row.get("baseline_overrides", []))
        candidate_skip = _one_skip(row.get("candidate_overrides", []))
        baseline_state = result_state(baseline_skip, expected_skip)
        candidate_state = result_state(candidate_skip, expected_skip)
        state_counts["baseline"][baseline_state] += 1
        state_counts["candidate"][candidate_state] += 1
        changed_value = baseline_skip != candidate_skip
        classification = classify_change(baseline_state, candidate_state, changed_value)
        if changed_value or classification != "unchanged":
            changes.append(
                {
                    "page_id": row["page_id"],
                    "key": list(key),
                    "expected_skip": expected_skip,
                    "baseline_skip": baseline_skip,
                    "candidate_skip": candidate_skip,
                    "baseline_state": baseline_state,
                    "candidate_state": candidate_state,
                    "classification": classification,
                    "baseline_rapidocr_calls": row.get("baseline_rapidocr_calls"),
                    "candidate_rapidocr_calls": row.get("candidate_rapidocr_calls"),
                    "candidate_decision_trace": row.get("candidate_decision_trace", []),
                }
            )

    if unmapped:
        baseline_exact = baseline_mismatch = candidate_exact = candidate_mismatch = candidate_absent = -1
    else:
        baseline_exact = state_counts["baseline"]["exact"]
        baseline_mismatch = state_counts["baseline"]["mismatch"]
        candidate_exact = state_counts["candidate"]["exact"]
        candidate_mismatch = state_counts["candidate"]["mismatch"]
        candidate_absent = state_counts["candidate"]["absent"]

    regressions = [row for row in changes if row["classification"] == "regression"]
    improvements = [row for row in changes if row["classification"] == "improvement"]
    changed_nonexact = [row for row in changes if row["classification"] == "changed_nonexact"]

    def page_candidate_exact(page_id: str) -> bool:
        page_rows = [row for row in records if row.get("page_id") == page_id]
        if not page_rows:
            return False
        for row in page_rows:
            key = tuple(int(value) for value in row["key"])
            expected_skip = expected.get(key)
            if expected_skip is None:
                return False
            if result_state(_one_skip(row.get("candidate_overrides", [])), expected_skip) != "exact":
                return False
        return True

    runtime = risk.get("runtime", {})
    candidate_calls = int(runtime.get("candidate_rapidocr_calls", 0))
    baseline_calls = int(runtime.get("baseline_rapidocr_calls", 0))
    risk_gates = risk.get("gates", {})

    # This is only a retained-positive projection.  The two baseline FNs are not
    # scanned here, so the full68 gate still requires an actual final MMR-only run.
    projected_fn_if_no_new_detections = EXPECTED_BASELINE_FULL_FN + candidate_absent
    payload = {
        "schema_version": "issue277.targeted_mmr_positive_risk_rescore.v1",
        "status": "completed",
        "execution_contract": {
            "inference_reexecuted": False,
            "production_code_modified": False,
            "risk_slice": str(risk_path),
            "accepted_issue264_rebase": str(accepted_path),
            "accepted_issue264_rebase_sha256": accepted_sha,
            "scope": "retained positive keys only; full68 negatives/FNs are not rescanned",
        },
        "summary": {
            "positive_records": len(records),
            "accepted_keys_mapped": len(records) - len(unmapped),
            "baseline": dict(state_counts["baseline"]),
            "candidate": dict(state_counts["candidate"]),
            "improvements": len(improvements),
            "regressions": len(regressions),
            "changed_nonexact": len(changed_nonexact),
            "projected_full68_fn_if_no_new_detections": projected_fn_if_no_new_detections,
            "baseline_rapidocr_calls": baseline_calls,
            "candidate_rapidocr_calls": candidate_calls,
            "rapidocr_call_delta_candidate_minus_j2": candidate_calls - baseline_calls,
        },
        "improvements": improvements,
        "regressions": regressions,
        "changed_nonexact": changed_nonexact,
        "all_changes": changes,
        "unmapped_keys": unmapped,
        "gates": {
            "all_175_positive_keys_have_accepted_expectations": not unmapped,
            "baseline_positive_contract_169_exact_6_mismatch": (
                baseline_exact == EXPECTED_BASELINE_EXACT
                and baseline_mismatch == EXPECTED_BASELINE_MISMATCH
                and state_counts["baseline"]["absent"] == 0
            ),
            "no_baseline_exact_regressions": not regressions,
            "candidate_exact_not_below_j2": candidate_exact >= baseline_exact,
            "candidate_mismatch_not_above_j2": candidate_mismatch <= baseline_mismatch,
            "projected_fn_not_above_3": projected_fn_if_no_new_detections <= 3,
            "page_025_candidate_gt_exact": page_candidate_exact("page_025"),
            "page_055_candidate_gt_exact": page_candidate_exact("page_055"),
            "page_042_candidate_gt_exact": page_candidate_exact("page_042"),
            "page_033_one_bar_fallback_semantics_exact": bool(
                risk_gates.get("page_033_one_bar_fallback_semantics_exact")
            ),
            "candidate_rapidocr_calls_below_j2": candidate_calls < baseline_calls,
        },
    }
    payload["all_positive_risk_acceptance_gates"] = all(payload["gates"].values())
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--risk-slice", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.risk_slice, args.accepted_rebase_report, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload["summary"],
                "gates": payload["gates"],
                "all_positive_risk_acceptance_gates": payload["all_positive_risk_acceptance_gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
