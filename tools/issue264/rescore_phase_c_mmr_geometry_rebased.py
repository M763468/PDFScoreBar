#!/usr/bin/env python3
"""Rescore an Issue #264 Phase C report after spatially rebasing historical MMR GT.

This command does not run detector, HOMR, CNN, OCR, SR, or numbering again. It
uses the completed Phase C artifacts and corrects only the evaluation coordinate
system: historical fixture indices are mapped by historical measure bbox onto the
current Phase A numbering geometry.

Historical fixture item count and current unique logical GT-event count are reported
separately because current Phase A grouping may merge multiple historical systems
that represented the same physical MMR.

The tool is intentionally host-only and lightweight: it depends only on Python's
standard library plus the evaluation-only rebase helper in this repository.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tools.issue264.phase_c_fixture_rebase import (
    mapping_method_counts,
    normalise_overrides,
    rebase_expected_overrides,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAGE_INDEX = PROJECT_ROOT / "logs/issue94_mmr_current_state/page_inputs.json"
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _override_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _override_skip(item: Mapping[str, Any]) -> int:
    return int(item.get("skip") or 0)


def _score_overrides(expected_payload: Any, detected_payload: Any) -> dict[str, Any]:
    expected = normalise_overrides(expected_payload)
    detected = normalise_overrides(detected_payload)
    expected_by_key = {_override_key(item): item for item in expected}
    detected_by_key = {_override_key(item): item for item in detected}

    matched: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []

    for key, expected_item in expected_by_key.items():
        detected_item = detected_by_key.get(key)
        if detected_item is None:
            missed.append({"key": list(key), "expected_skip": _override_skip(expected_item)})
            continue
        if _override_skip(expected_item) == _override_skip(detected_item):
            matched.append({"key": list(key), "skip": _override_skip(detected_item)})
        else:
            mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": _override_skip(expected_item),
                    "detected_skip": _override_skip(detected_item),
                    "detected_comment": detected_item.get("comment"),
                }
            )

    for key, detected_item in detected_by_key.items():
        if key not in expected_by_key:
            unexpected.append(
                {
                    "key": list(key),
                    "detected_skip": _override_skip(detected_item),
                    "detected_comment": detected_item.get("comment"),
                }
            )

    return {
        "counts": {
            "expected": len(expected),
            "detected": len(detected),
            "matched_tp": len(matched),
            "missed_fn": len(missed),
            "skip_mismatch": len(mismatch),
            "unexpected_fp": len(unexpected),
        },
        "matched": matched,
        "missed": missed,
        "skip_mismatch": mismatch,
        "unexpected": unexpected,
    }


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
    payload = _load_json(path)
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
    keys = (
        "expected",
        "detected",
        "matched_tp",
        "missed_fn",
        "skip_mismatch",
        "unexpected_fp",
    )
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
    totals["f1"] = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return totals


def run(report_path: Path, output_path: Path | None = None) -> Path:
    report = _load_json(report_path)
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
    source_fixture_items = 0
    coalesced_equivalent_items = 0

    for raw_page in raw_pages:
        if not isinstance(raw_page, Mapping):
            raise ValueError("Malformed Phase C page report")
        page_id = str(raw_page["page_id"])
        global_index = int(raw_page["global_index"])
        fixture_path = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
        expected_payload: Any = (
            _load_json(fixture_path) if fixture_path.is_file() else {"overrides": []}
        )
        source_page_items = len(normalise_overrides(expected_payload))
        source_fixture_items += source_page_items

        artifact = artifacts.get(page_id)
        if artifact is None:
            raise ValueError(f"Missing generated artifacts for {page_id}")
        current_numbering = _load_json(_artifact_path(artifact, "numbering_base"))
        detected_payload = _load_json(_artifact_path(artifact, "overrides_mmr"))

        mappings: list[dict[str, Any]] = []
        if fixture_path.is_file():
            page_input = page_inputs.get(page_id)
            if page_input is None or not page_input.get("numbering_base"):
                raise ValueError(f"Missing historical numbering_base mapping for {page_id}")
            historical_numbering_path = _resolve_project_path(str(page_input["numbering_base"]))
            historical_numbering = _load_json(historical_numbering_path)
            expected_payload, mappings = rebase_expected_overrides(
                expected_payload,
                historical_numbering,
                current_numbering,
                global_page_index=global_index,
            )
            for mapping in mappings:
                mapping["page_id"] = page_id
            changed_keys += sum(bool(mapping["changed"]) for mapping in mappings)
            coalesced_equivalent_items += sum(
                bool(mapping["coalesced_equivalent_fixture"]) for mapping in mappings
            )
            all_mappings.extend(mappings)

        scoring = _score_overrides(expected_payload, detected_payload)
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
                    "source_fixture_items": source_page_items,
                    "rebased_unique_expected": scoring["counts"]["expected"],
                    "mapping_count": len(mappings),
                    "changed_key_count": sum(bool(mapping["changed"]) for mapping in mappings),
                    "coalesced_equivalent_items": sum(
                        bool(mapping["coalesced_equivalent_fixture"]) for mapping in mappings
                    ),
                    "mappings": mappings,
                },
            }
        )

    totals = _summary_totals(page_reports)
    gates = {
        "page_count_68": totals["pages"] == 68,
        "historical_source_fixture_items_182": source_fixture_items == 182,
        "fixture_rebase_mapped_all_182_source_items": len(all_mappings) == 182,
        "rebased_unique_expected_not_above_source": totals["expected"] <= source_fixture_items,
        "zero_expected_pages_scored": totals["zero_expected_pages"] == 16,
        "zero_expected_page_detections_zero": totals["zero_expected_page_detections"] == 0,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
    }

    rebased_report = {
        "schema": "issue264.phase_c_mmr_geometry_rebased_score.v2",
        "status": "passed" if all(gates.values()) else "failed",
        "source_report": str(report_path),
        "source_git_head": report.get("repository", {}).get("git_head"),
        "evaluation_contract": {
            "historical_numbering_geometry_use": "evaluation-only fixture bbox rebase",
            "historical_numbering_as_production_input": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "mmr_reexecuted": False,
            "numbering_reexecuted": False,
            "current_phase_a_numbering_artifacts_reused": True,
            "current_mmr_override_artifacts_reused": True,
            "equivalent_historical_fixture_items_after_current_system_merge": (
                "coalesce when current key and skip are equal; reject conflicting skip"
            ),
        },
        "original_direct_index_summary": report.get("current"),
        "historical_source_fixture_items": source_fixture_items,
        "geometry_rebased_summary": totals,
        "fixture_rebase": {
            "mapped_historical_source_items": len(all_mappings),
            "rebased_unique_expected_events": totals["expected"],
            "coalesced_equivalent_source_items": coalesced_equivalent_items,
            "changed_index_keys": changed_keys,
            "unchanged_index_keys": len(all_mappings) - changed_keys,
            "mapping_methods": mapping_method_counts(all_mappings),
        },
        "gates": gates,
        "pages": page_reports,
    }

    if output_path is None:
        output_path = report_path.with_name("phase_c_mmr_geometry_rebased_score_report.json")
    _write_json(output_path, rebased_report)
    print(
        json.dumps(
            {
                "status": rebased_report["status"],
                "historical_source_fixture_items": source_fixture_items,
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
    payload = _load_json(output)
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
