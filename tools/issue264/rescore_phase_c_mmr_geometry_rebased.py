#!/usr/bin/env python3
"""Rescore an Issue #264 Phase C report after spatially rebasing historical MMR GT.

This command does not run detector, HOMR, CNN, OCR, SR, or numbering again.  It
uses the completed Phase C artifacts and corrects only the evaluation coordinate
system: historical fixture indices are mapped by historical measure bbox onto the
current Phase A numbering geometry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from src.pipeline.utils.io import load_json, write_json
from tools.issue264.phase_c_fixture_rebase import (
    mapping_method_counts,
    rebase_expected_overrides,
)
from tools.issue264.run_phase_c_mmr_regression import score_overrides

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAGE_INDEX = PROJECT_ROOT / "logs/issue94_mmr_current_state/page_inputs.json"
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures"


def _resolve_project_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_file():
        return raw
    if not raw.is_absolute():
        candidate = PROJECT_ROOT / raw
        if candidate.is_file():
            return candidate
    parts = raw.parts
    if "ws_PDFScoreBar" in parts:
        index = parts.index("ws_PDFScoreBar")
        candidate = PROJECT_ROOT.joinpath(*parts[index + 1 :])
        if candidate.is_file():
            return candidate
    if "/workspace/" in str(raw):
        suffix = str(raw).split("/workspace/", 1)[1]
        candidate = PROJECT_ROOT / suffix
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(raw)


def _page_inputs(path: Path) -> dict[str, Mapping[str, Any]]:
    payload = load_json(path)
    pages = payload.get("pages") if isinstance(payload, Mapping) else None
    if not isinstance(pages, list):
        raise ValueError(f"Page index lacks pages list: {path}")
    result: dict[str, Mapping[str, Any]] = {}
    for item in pages:
        if not isinstance(item, Mapping):
            raise ValueError("Malformed page index entry")
        page_id = str(item.get("page_id", ""))
        result[page_id] = item
    return result


def _artifact_index(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    artifacts = report.get("generated_artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Phase C report lacks generated_artifacts")
    result: dict[str, Mapping[str, Any]] = {}
    for item in artifacts:
        if isinstance(item, Mapping):
            result[str(item.get("page_id", ""))] = item
    return result


def _artifact_path(item: Mapping[str, Any], key: str) -> Path:
    detail = item.get(key)
    if not isinstance(detail, Mapping) or not detail.get("path"):
        raise ValueError(f"Generated artifact lacks {key}")
    return _resolve_project_path(str(detail["path"]))


def _summary_totals(page_reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    keys = ("expected", "detected", "matched_tp", "missed_fn", "skip_mismatch", "unexpected_fp")
    totals = {key: 0 for key in keys}
    for page in page_reports:
        counts = page["scoring"]["counts"]
        for key in keys:
            totals[key] += int(counts[key])
    totals["pages"] = len(page_reports)
    totals["zero_expected_pages"] = sum(
        1 for page in page_reports if int(page["scoring"]["counts"]["expected"]) == 0
    )
    totals["zero_expected_page_detections"] = sum(
        int(page["scoring"]["counts"]["detected"])
        for page in page_reports
        if int(page["scoring"]["counts"]["expected"]) == 0
    )
    detected = totals["detected"]
    expected = totals["expected"]
    matched = totals["matched_tp"]
    precision = matched / detected if detected else 0.0
    recall = matched / expected if expected else 0.0
    totals["precision"] = precision
    totals["recall"] = recall
    totals["f1"] = (
        2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    )
    return totals


def run(report_path: Path, output_path: Path | None = None) -> Path:
    report = load_json(report_path)
    if not isinstance(report, Mapping):
        raise ValueError(f"Malformed Phase C report: {report_path}")

    page_inputs = _page_inputs(DEFAULT_PAGE_INDEX)
    artifacts = _artifact_index(report)
    raw_pages = report.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != 68:
        raise ValueError("Expected a completed 68-page Phase C report")

    page_reports: list[dict[str, Any]] = []
    all_mappings: list[dict[str, Any]] = []
    changed_keys = 0

    for raw_page in raw_pages:
        if not isinstance(raw_page, Mapping):
            raise ValueError("Malformed Phase C page report")
        page_id = str(raw_page["page_id"])
        global_index = int(raw_page["global_index"])
        fixture_path = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
        expected_payload: Any = load_json(fixture_path) if fixture_path.is_file() else {"overrides": []}

        artifact = artifacts.get(page_id)
        if artifact is None:
            raise ValueError(f"Missing generated artifacts for {page_id}")
        current_numbering = load_json(_artifact_path(artifact, "numbering_base"))
        detected_payload = load_json(_artifact_path(artifact, "overrides_mmr"))

        mappings: list[dict[str, Any]] = []
        if fixture_path.is_file():
            page_input = page_inputs.get(page_id)
            if page_input is None or not page_input.get("numbering_base"):
                raise ValueError(f"Missing historical numbering_base mapping for {page_id}")
            historical_numbering_path = _resolve_project_path(str(page_input["numbering_base"]))
            historical_numbering = load_json(historical_numbering_path)
            expected_payload, mappings = rebase_expected_overrides(
                expected_payload,
                historical_numbering,
                current_numbering,
                global_page_index=global_index,
            )
            for mapping in mappings:
                mapping["page_id"] = page_id
            changed_keys += sum(bool(mapping["changed"]) for mapping in mappings)
            all_mappings.extend(mappings)

        scoring = score_overrides(expected_payload, detected_payload)
        page_reports.append(
            {
                "page_id": page_id,
                "global_index": global_index,
                "score": raw_page.get("score"),
                "score_page": raw_page.get("score_page"),
                "direct_index_scoring": raw_page.get("scoring"),
                "scoring": scoring,
                "fixture_rebase": {
                    "fixture_present": fixture_path.is_file(),
                    "mapping_count": len(mappings),
                    "changed_key_count": sum(bool(mapping["changed"]) for mapping in mappings),
                    "mappings": mappings,
                },
            }
        )

    totals = _summary_totals(page_reports)
    gates = {
        "page_count_68": totals["pages"] == 68,
        "expected_fixture_total_182": totals["expected"] == 182,
        "fixture_rebase_complete_182": len(all_mappings) == 182,
        "zero_expected_pages_scored": totals["zero_expected_pages"] == 16,
        "zero_expected_page_detections_zero": totals["zero_expected_page_detections"] == 0,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
    }

    rebased_report = {
        "schema": "issue264.phase_c_mmr_geometry_rebased_score.v1",
        "status": "passed" if all(gates.values()) else "failed",
        "source_report": str(report_path),
        "source_git_head": report.get("repository", {}).get("git_head"),
        "evaluation_contract": {
            "historical_numbering_geometry_use": "evaluation-only fixture bbox rebase",
            "historical_numbering_as_production_input": False,
            "detector_reexecuted": False,
            "mmr_reexecuted": False,
            "current_phase_a_numbering_artifacts_reused": True,
            "current_mmr_override_artifacts_reused": True,
        },
        "original_direct_index_summary": report.get("current"),
        "geometry_rebased_summary": totals,
        "fixture_rebase": {
            "mapped_expected_overrides": len(all_mappings),
            "changed_index_keys": changed_keys,
            "unchanged_index_keys": len(all_mappings) - changed_keys,
            "mapping_methods": mapping_method_counts(all_mappings),
        },
        "gates": gates,
        "pages": page_reports,
    }

    if output_path is None:
        output_path = report_path.with_name("phase_c_mmr_geometry_rebased_score_report.json")
    write_json(output_path, rebased_report)
    print(
        json.dumps(
            {
                "status": rebased_report["status"],
                "geometry_rebased_summary": totals,
                "fixture_rebase": rebased_report["fixture_rebase"],
                "gates": gates,
            },
            indent=2,
        )
    )
    print(f"report: {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = run(args.report, args.output)
    payload = load_json(output)
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
