#!/usr/bin/env python3
"""Score the Issue #277 targeted MMR full-68 run in the accepted geometry frame.

No inference is executed.  The canonical accepted Issue #264 geometry-rebased
report supplies the physical expected key/skip contract.  This scorer evaluates
all 68 pages, including the historical false negatives and zero-fixture pages,
and also requires the already-passed retained-positive risk slice as a focused
causal guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ACCEPTED_REBASE_SHA256 = "83bbe96b34fb9357c8c9ebaf29a1cce48296040306650091555a2e4ffad12471"
EXPECTED_PAGES = 68
EXPECTED_GT_EVENTS = 177
EXPECTED_ZERO_FIXTURE_PAGES = 16
J2_REFERENCE = {
    "detected": 175,
    "matched_tp": 169,
    "missed_fn": 2,
    "skip_mismatch": 6,
    "unexpected_fp": 0,
}
DEFAULT_POSITIVE_RISK_RESCORE = (
    PROJECT_ROOT
    / "logs/issue277/issue277_targeted_positive_risk_slice_01/"
    "targeted_mmr_positive_risk_rescore_01.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_targeted_full68_01/"
    "targeted_mmr_full68_rescore_01.json"
)


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


def accepted_expected_index(report: Mapping[str, Any]) -> dict[tuple[int, int, int], int]:
    """Recover the canonical rebased expected key/skip map from #264 scoring."""

    expected: dict[tuple[int, int, int], int] = {}
    for page in report.get("pages", []):
        scoring = page.get("scoring", {})
        rows: list[tuple[Mapping[str, Any], str]] = []
        rows.extend((row, "skip") for row in scoring.get("matched", []))
        rows.extend((row, "expected_skip") for row in scoring.get("missed", []))
        rows.extend((row, "expected_skip") for row in scoring.get("skip_mismatch", []))
        for row, field in rows:
            key = tuple(int(value) for value in row["key"])
            skip = int(row[field])
            previous = expected.get(key)
            if previous is not None and previous != skip:
                raise RuntimeError(f"Conflicting accepted expectation for {key}: {previous} vs {skip}")
            expected[key] = skip
    return expected


def actual_override_index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[int, int, int], Mapping[str, Any]]:
    """Index full-68 overrides and reject duplicate logical keys."""

    actual: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    for row in rows:
        key = (int(row["page"]), int(row["system"]), int(row["measure"]))
        if key in actual:
            raise RuntimeError(f"Duplicate full68 override key: {key}")
        actual[key] = row
    return actual


def score_indices(
    expected: Mapping[tuple[int, int, int], int],
    actual: Mapping[tuple[int, int, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """Score exact/missed/mismatch/unexpected events in one coordinate frame."""

    matched: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []

    for key, expected_skip in sorted(expected.items()):
        row = actual.get(key)
        if row is None:
            missed.append({"key": list(key), "expected_skip": int(expected_skip)})
            continue
        detected_skip = int(row.get("skip") or 0)
        if detected_skip == int(expected_skip):
            matched.append({"key": list(key), "skip": detected_skip})
        else:
            mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": int(expected_skip),
                    "detected_skip": detected_skip,
                    "detected_comment": row.get("comment"),
                }
            )

    for key, row in sorted(actual.items()):
        if key in expected:
            continue
        unexpected.append(
            {
                "key": list(key),
                "detected_skip": int(row.get("skip") or 0),
                "detected_comment": row.get("comment"),
            }
        )

    counts = {
        "expected": len(expected),
        "detected": len(actual),
        "matched_tp": len(matched),
        "missed_fn": len(missed),
        "skip_mismatch": len(mismatch),
        "unexpected_fp": len(unexpected),
    }
    return {
        "counts": counts,
        "matched": matched,
        "missed": missed,
        "skip_mismatch": mismatch,
        "unexpected": unexpected,
    }


def page_exact(
    *,
    page_index: int,
    expected: Mapping[tuple[int, int, int], int],
    actual: Mapping[tuple[int, int, int], Mapping[str, Any]],
    expected_count: int | None = None,
) -> bool:
    expected_rows = {key: skip for key, skip in expected.items() if key[0] == page_index}
    actual_rows = {key: row for key, row in actual.items() if key[0] == page_index}
    if expected_count is not None and len(expected_rows) != expected_count:
        return False
    if not expected_rows:
        return not actual_rows
    if set(expected_rows) != set(actual_rows):
        return False
    return all(int(actual_rows[key].get("skip") or 0) == skip for key, skip in expected_rows.items())


def zero_expected_pages(expected: Mapping[tuple[int, int, int], int]) -> list[int]:
    positive_pages = {key[0] for key in expected}
    return [page for page in range(EXPECTED_PAGES) if page not in positive_pages]


def run(
    run_path: Path,
    accepted_path: Path,
    positive_risk_path: Path,
    output_path: Path,
    candidate_schema: str = "issue277.targeted_mmr_full68.v1",
    candidate_name: str = "targeted",
) -> dict[str, Any]:
    candidate = _load_json(run_path)
    accepted = _load_json(accepted_path)
    positive_risk = _load_json(positive_risk_path)

    if not isinstance(candidate, Mapping) or candidate.get("status") != "completed":
        raise ValueError(f"{candidate_name} full68 report is not completed")
    if candidate.get("schema_version") != candidate_schema:
        raise ValueError(f"Unexpected {candidate_name} full68 schema")
    if not isinstance(accepted, Mapping) or accepted.get("status") != "passed":
        raise ValueError("Accepted Issue #264 rebase report is not passed")
    if not isinstance(positive_risk, Mapping) or positive_risk.get("status") != "completed":
        raise ValueError("Positive-risk rescore is not completed")

    accepted_sha = _sha256(accepted_path)
    if accepted_sha != ACCEPTED_REBASE_SHA256:
        raise RuntimeError(
            f"Accepted rebase fingerprint mismatch: {accepted_sha} != {ACCEPTED_REBASE_SHA256}"
        )
    accepted_summary = accepted.get("geometry_rebased_summary", {})
    if int(accepted_summary.get("expected", -1)) != EXPECTED_GT_EVENTS:
        raise RuntimeError("Accepted rebase expected-event count is not canonical 177")
    if positive_risk.get("execution_contract", {}).get("accepted_issue264_rebase_sha256") != accepted_sha:
        raise RuntimeError("Positive-risk rescore used a different accepted #264 rebase")

    pages = candidate.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("Targeted full68 report lacks pages list")
    page_ids = [str(row.get("page_id")) for row in pages if isinstance(row, Mapping)]
    expected_page_ids = [f"page_{index:03d}" for index in range(1, EXPECTED_PAGES + 1)]
    page_order_exact = page_ids == expected_page_ids

    expected = accepted_expected_index(accepted)
    if len(expected) != EXPECTED_GT_EVENTS:
        raise RuntimeError(f"Expected {EXPECTED_GT_EVENTS} canonical events, got {len(expected)}")
    actual = actual_override_index(
        [row for row in candidate.get("all_overrides", []) if isinstance(row, Mapping)]
    )
    scoring = score_indices(expected, actual)
    counts = scoring["counts"]

    zero_pages = zero_expected_pages(expected)
    zero_page_detections = [
        page
        for page in zero_pages
        if any(key[0] == page for key in actual)
    ]

    runtime = candidate.get("runtime", {})
    execution = candidate.get("execution_contract", {})
    positive_risk_pass = bool(positive_risk.get("all_positive_risk_acceptance_gates"))

    gates = {
        "page_count_68": len(pages) == EXPECTED_PAGES,
        "page_order_exact": page_order_exact,
        "accepted_rebase_fingerprint_canonical": accepted_sha == ACCEPTED_REBASE_SHA256,
        "expected_event_count_177": counts["expected"] == EXPECTED_GT_EVENTS,
        "positive_risk_acceptance_passed": positive_risk_pass,
        "candidate_rapidocr_cuda_confirmed": bool(runtime.get("rapidocr_cuda_confirmed")),
        "candidate_no_upstream_rerun": all(
            not bool(execution.get(key))
            for key in (
                "detector_reexecuted",
                "homr_reexecuted",
                "sr_reexecuted",
                "omr_reexecuted",
                "grouping_reexecuted",
                "numbering_reexecuted",
            )
        ),
        "unexpected_fp_zero": counts["unexpected_fp"] == 0,
        "missed_fn_not_above_3": counts["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": counts["skip_mismatch"] <= 6,
        "not_worse_than_j2_tp": counts["matched_tp"] >= J2_REFERENCE["matched_tp"],
        "not_worse_than_j2_fn": counts["missed_fn"] <= J2_REFERENCE["missed_fn"],
        "not_worse_than_j2_mismatch": counts["skip_mismatch"] <= J2_REFERENCE["skip_mismatch"],
        "zero_fixture_page_count_16": len(zero_pages) == EXPECTED_ZERO_FIXTURE_PAGES,
        "zero_fixture_pages_detection_empty": not zero_page_detections,
        "page_025_exact": page_exact(page_index=24, expected=expected, actual=actual),
        "page_055_exact": page_exact(page_index=54, expected=expected, actual=actual),
        "page_042_five_overrides_exact": page_exact(
            page_index=41, expected=expected, actual=actual, expected_count=5
        ),
        "page_033_expected_exact_no_fp": page_exact(page_index=32, expected=expected, actual=actual),
        "page_033_no_system0_measure0_override": (32, 0, 0) not in actual,
    }

    payload = {
        "schema_version": "issue277.targeted_mmr_full68_rescore.v1",
        "status": "completed",
        "execution_contract": {
            "inference_reexecuted": False,
            "production_code_modified": False,
            "targeted_full68_run": str(run_path),
            "accepted_issue264_rebase": str(accepted_path),
            "accepted_issue264_rebase_sha256": accepted_sha,
            "positive_risk_rescore": str(positive_risk_path),
        },
        "j2_reference": J2_REFERENCE,
        "summary": {
            **counts,
            "zero_fixture_pages": len(zero_pages),
            "zero_fixture_page_detections": len(zero_page_detections),
            "rapidocr_calls": runtime.get("rapidocr_calls"),
            "classifier_calls": runtime.get("classifier_calls"),
            "elapsed_sec": runtime.get("elapsed_sec"),
            "positive_risk_baseline_calls": positive_risk.get("summary", {}).get("baseline_rapidocr_calls"),
            "positive_risk_candidate_calls": positive_risk.get("summary", {}).get("candidate_rapidocr_calls"),
            "positive_risk_call_delta": positive_risk.get("summary", {}).get("rapidocr_call_delta_candidate_minus_j2"),
        },
        "scoring": scoring,
        "zero_fixture_page_indices": zero_pages,
        "zero_fixture_page_detections": zero_page_detections,
        "gates": gates,
    }
    payload["all_full68_acceptance_gates"] = all(gates.values())
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument(
        "--positive-risk-rescore",
        type=Path,
        default=DEFAULT_POSITIVE_RISK_RESCORE,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = run(args.run, args.accepted_rebase_report, args.positive_risk_rescore, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload["summary"],
                "gates": payload["gates"],
                "all_full68_acceptance_gates": payload["all_full68_acceptance_gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
