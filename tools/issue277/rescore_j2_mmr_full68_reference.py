#!/usr/bin/env python3
"""Score the directly comparable merged-J2 full68 reference for Issue #277."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue277.rescore_targeted_mmr_full68 import (
    ACCEPTED_REBASE_SHA256,
    EXPECTED_GT_EVENTS,
    EXPECTED_PAGES,
    EXPECTED_ZERO_FIXTURE_PAGES,
    J2_REFERENCE,
    accepted_expected_index,
    actual_override_index,
    page_exact,
    score_indices,
    zero_expected_pages,
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


def run(run_path: Path, accepted_path: Path, output_path: Path) -> dict[str, Any]:
    reference = _load_json(run_path)
    accepted = _load_json(accepted_path)
    if reference.get("schema_version") != "issue277.j2_mmr_full68_reference.v1":
        raise ValueError("Unexpected J2 reference schema")
    if reference.get("status") != "completed":
        raise ValueError("J2 reference run is not completed")
    if not isinstance(accepted, Mapping) or accepted.get("status") != "passed":
        raise ValueError("Accepted Issue #264 rebase report is not passed")

    accepted_sha = _sha256(accepted_path)
    if accepted_sha != ACCEPTED_REBASE_SHA256:
        raise RuntimeError("Accepted Issue #264 rebase fingerprint mismatch")
    expected = accepted_expected_index(accepted)
    if len(expected) != EXPECTED_GT_EVENTS:
        raise RuntimeError(f"Expected {EXPECTED_GT_EVENTS} canonical events, got {len(expected)}")

    pages = reference.get("pages", [])
    actual = actual_override_index(
        [row for row in reference.get("all_overrides", []) if isinstance(row, Mapping)]
    )
    scoring = score_indices(expected, actual)
    counts = scoring["counts"]
    zero_pages = zero_expected_pages(expected)
    zero_detections = [page for page in zero_pages if any(key[0] == page for key in actual)]
    runtime = reference.get("runtime", {})
    execution = reference.get("execution_contract", {})

    gates = {
        "page_count_68": len(pages) == EXPECTED_PAGES,
        "accepted_rebase_fingerprint_canonical": accepted_sha == ACCEPTED_REBASE_SHA256,
        "exact_merged_j2_reference_metrics": all(
            int(counts[key]) == int(value) for key, value in J2_REFERENCE.items()
        ),
        "zero_fixture_page_count_16": len(zero_pages) == EXPECTED_ZERO_FIXTURE_PAGES,
        "zero_fixture_pages_detection_empty": not zero_detections,
        "page_025_exact": page_exact(page_index=24, expected=expected, actual=actual),
        "page_055_exact": page_exact(page_index=54, expected=expected, actual=actual),
        "page_042_five_overrides_exact": page_exact(
            page_index=41, expected=expected, actual=actual, expected_count=5
        ),
        "page_033_expected_exact_no_fp": page_exact(page_index=32, expected=expected, actual=actual),
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
    }
    payload = {
        "schema_version": "issue277.j2_mmr_full68_reference_rescore.v1",
        "status": "completed",
        "execution_contract": {
            "inference_reexecuted": False,
            "production_code_modified": False,
            "reference_run": str(run_path),
            "accepted_issue264_rebase": str(accepted_path),
            "accepted_issue264_rebase_sha256": accepted_sha,
        },
        "summary": {
            **counts,
            "zero_fixture_pages": len(zero_pages),
            "zero_fixture_page_detections": len(zero_detections),
            "rapidocr_calls": runtime.get("rapidocr_calls"),
            "classifier_calls": runtime.get("classifier_calls"),
            "elapsed_sec": runtime.get("elapsed_sec"),
        },
        "gates": gates,
        "all_reference_gates": all(gates.values()),
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.run, args.accepted_rebase_report, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload["summary"],
                "gates": payload["gates"],
                "all_reference_gates": payload["all_reference_gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
