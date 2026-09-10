#!/usr/bin/env python3
"""Rescore the direct MMRProcessor Issue #277 production full68 run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue277 import rescore_targeted_mmr_full68 as base

DEFAULT_RUN = (
    PROJECT_ROOT / "logs/issue277/issue277_production_full68_01/production_mmr_full68_01.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_production_full68_01/production_mmr_full68_rescore_01.json"
)
DEFAULT_ACCEPTED_GEOMETRY_REPORT = (
    Path("/home/masaki_muramatsu/ws_PDFScoreBar")
    / "logs/issue276_j2_full68_correct/geometry_rebased.json"
)
DEFAULT_CANONICAL_RESCORE = (
    Path("/home/masaki_muramatsu/ws_PDFScoreBar")
    / "logs/issue277/issue277_targeted_full68_01/targeted_mmr_full68_rescore_01.json"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_expected_index(rescore: Mapping[str, Any]) -> dict[tuple[int, int, int], int]:
    scoring = rescore.get("scoring", {})
    expected = {tuple(row["key"]): int(row["skip"]) for row in scoring.get("matched", [])}
    expected.update(
        {tuple(row["key"]): int(row["expected_skip"]) for row in scoring.get("missed", [])}
    )
    expected.update(
        {
            tuple(row["key"]): int(row["expected_skip"])
            for row in scoring.get("skip_mismatch", [])
        }
    )
    return expected


def run(
    run_path: Path,
    accepted_geometry_path: Path,
    canonical_rescore_path: Path,
    positive_risk_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    candidate = _load_json(run_path)
    accepted = _load_json(accepted_geometry_path)
    canonical_rescore = _load_json(canonical_rescore_path)
    positive_risk = _load_json(positive_risk_path)
    if candidate.get("schema_version") != "issue277.production_mmr_full68.v1":
        raise ValueError("Unexpected production full68 schema")
    if candidate.get("status") != "completed":
        raise ValueError("Production full68 report is not completed")
    if accepted.get("status") != "passed":
        raise ValueError("Accepted geometry report is not passed")

    expected = base.accepted_expected_index(accepted)
    canonical_expected = _canonical_expected_index(canonical_rescore)
    if expected != canonical_expected or len(expected) != base.EXPECTED_GT_EVENTS:
        raise RuntimeError("Accepted geometry map does not equal the canonical #264 expected map")
    if canonical_rescore.get("execution_contract", {}).get("accepted_issue264_rebase_sha256") != (
        base.ACCEPTED_REBASE_SHA256
    ):
        raise RuntimeError("Canonical rescore does not reference the accepted #264 fingerprint")

    actual = base.actual_override_index(candidate.get("all_overrides", []))
    scoring = base.score_indices(expected, actual)
    counts = scoring["counts"]
    zero_pages = base.zero_expected_pages(expected)
    zero_page_detections = [page for page in zero_pages if any(key[0] == page for key in actual)]
    runtime = candidate["runtime"]
    execution = candidate["execution_contract"]
    gates = {
        "processor_is_direct_production_mmrprocessor": execution.get("processor_class")
        == "src.measure_numbering.mmr.MMRProcessor",
        "targeted_retry_processor_not_used": execution.get("targeted_retry_processor_used") is False,
        "page_count_68": len(candidate.get("pages", [])) == base.EXPECTED_PAGES,
        "expected_event_count_177": counts["expected"] == base.EXPECTED_GT_EVENTS,
        "accepted_geometry_map_equals_canonical_issue264": expected == canonical_expected,
        "rapidocr_cuda_confirmed": bool(runtime.get("rapidocr_cuda_confirmed")),
        "no_upstream_rerun": all(
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
        "matched_tp_at_least_169": counts["matched_tp"] >= 169,
        "missed_fn_not_above_3": counts["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": counts["skip_mismatch"] <= 6,
        "zero_fixture_page_count_16": len(zero_pages) == base.EXPECTED_ZERO_FIXTURE_PAGES,
        "zero_fixture_pages_detection_empty": not zero_page_detections,
        "page_025_exact": base.page_exact(page_index=24, expected=expected, actual=actual),
        "page_055_exact": base.page_exact(page_index=54, expected=expected, actual=actual),
        "page_042_five_overrides_exact": base.page_exact(
            page_index=41, expected=expected, actual=actual, expected_count=5
        ),
        "page_033_expected_exact_no_fp": base.page_exact(page_index=32, expected=expected, actual=actual),
        "page_033_no_system0_measure0_override": (32, 0, 0) not in actual,
        "positive_risk_acceptance_passed": bool(
            positive_risk.get("all_positive_risk_acceptance_gates")
        ),
    }
    payload = {
        "schema_version": "issue277.production_mmr_full68_rescore.v1",
        "status": "completed",
        "execution_contract": {
            "inference_reexecuted": False,
            "production_run": str(run_path),
            "accepted_geometry_report": str(accepted_geometry_path),
            "canonical_issue264_rescore": str(canonical_rescore_path),
            "canonical_issue264_rebase_sha256": base.ACCEPTED_REBASE_SHA256,
            "positive_risk_rescore": str(positive_risk_path),
        },
        "summary": {
            **counts,
            "zero_fixture_pages": len(zero_pages),
            "zero_fixture_page_detections": len(zero_page_detections),
            "rapidocr_calls": runtime.get("rapidocr_calls"),
            "classifier_calls": runtime.get("classifier_calls"),
            "elapsed_sec": runtime.get("elapsed_sec"),
        },
        "scoring": scoring,
        "zero_fixture_page_indices": zero_pages,
        "zero_fixture_page_detections": zero_page_detections,
        "gates": gates,
    }
    payload["all_full68_acceptance_gates"] = all(gates.values())
    base._write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--accepted-geometry-report", type=Path, default=DEFAULT_ACCEPTED_GEOMETRY_REPORT)
    parser.add_argument("--canonical-rescore", type=Path, default=DEFAULT_CANONICAL_RESCORE)
    parser.add_argument(
        "--positive-risk-rescore", type=Path, default=base.DEFAULT_POSITIVE_RISK_RESCORE
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = run(
        args.run,
        args.accepted_geometry_report,
        args.canonical_rescore,
        args.positive_risk_rescore,
        args.output,
    )
    print(
        {
            "status": payload["status"],
            "summary": payload["summary"],
            "gates": payload["gates"],
            "all_full68_acceptance_gates": payload["all_full68_acceptance_gates"],
            "output": str(args.output),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
