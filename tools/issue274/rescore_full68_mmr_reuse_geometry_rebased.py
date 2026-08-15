#!/usr/bin/env python3
"""Rescore completed Issue #274 full-68 MMR artifacts with rebased fixture geometry.

This is evaluation-only: it reads historical fixtures, historical numbering,
current retained Phase-A numbering, and completed MMR override artifacts. It
never invokes detector, HOMR, SR, OMR-DLN, numbering, CUDA, CNN, or OCR.
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
DEFAULT_REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
DEFAULT_ACCEPTED_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
DEFAULT_PAGE_INPUTS = PROJECT_ROOT / "logs/issue94_mmr_current_state/page_inputs.json"
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_project_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_file():
        return raw
    if not raw.is_absolute():
        candidate = PROJECT_ROOT / raw
        if candidate.is_file():
            return candidate
    if "/workspace/" in str(raw):
        candidate = PROJECT_ROOT / str(raw).split("/workspace/", 1)[1]
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(raw)


def _page_inputs(path: Path) -> list[Mapping[str, Any]]:
    payload = _load_json(path)
    pages = payload.get("pages") if isinstance(payload, Mapping) else None
    if not isinstance(pages, list) or len(pages) != 68:
        raise ValueError(f"Expected 68 historical page inputs: {path}")
    expected_ids = [f"page_{index:03d}" for index in range(1, 69)]
    if [
        str(page.get("page_id", "")) for page in pages if isinstance(page, Mapping)
    ] != expected_ids:
        raise ValueError("Historical page inputs are not the unique page_001..page_068 sequence")
    return pages


def _key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _skip(item: Mapping[str, Any]) -> int:
    return int(item.get("skip") or 0)


def _index(payload: Any) -> dict[tuple[int, int, int], dict[str, Any]]:
    return {_key(item): item for item in normalise_overrides(payload)}


def _semantic_index(payload: Any) -> dict[tuple[int, int, int], int]:
    return {key: _skip(item) for key, item in _index(payload).items()}


def _score(expected_payload: Any, detected_payload: Any) -> dict[str, Any]:
    expected_by_key = _index(expected_payload)
    detected_by_key = _index(detected_payload)
    matched, missed, mismatch, unexpected = [], [], [], []
    for key, expected in expected_by_key.items():
        detected = detected_by_key.get(key)
        if detected is None:
            missed.append({"key": list(key), "expected_skip": _skip(expected)})
        elif _skip(expected) == _skip(detected):
            matched.append({"key": list(key), "skip": _skip(detected)})
        else:
            mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": _skip(expected),
                    "detected_skip": _skip(detected),
                    "detected_comment": detected.get("comment"),
                }
            )
    for key, detected in detected_by_key.items():
        if key not in expected_by_key:
            unexpected.append(
                {
                    "key": list(key),
                    "detected_skip": _skip(detected),
                    "detected_comment": detected.get("comment"),
                }
            )
    return {
        "counts": {
            "expected": len(expected_by_key),
            "detected": len(detected_by_key),
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


def _summary(pages: list[Mapping[str, Any]]) -> dict[str, Any]:
    names = (
        "expected",
        "detected",
        "matched_tp",
        "missed_fn",
        "skip_mismatch",
        "unexpected_fp",
    )
    totals = {
        name: sum(int(page["scoring"]["counts"][name]) for page in pages) for name in names
    }
    totals["pages"] = len(pages)
    totals["zero_expected_pages"] = sum(
        int(page["scoring"]["counts"]["expected"]) == 0 for page in pages
    )
    totals["zero_expected_page_detections"] = sum(
        int(page["scoring"]["counts"]["detected"])
        for page in pages
        if int(page["scoring"]["counts"]["expected"]) == 0
    )
    totals["precision"] = (
        totals["matched_tp"] / totals["detected"] if totals["detected"] else 0.0
    )
    totals["recall"] = (
        totals["matched_tp"] / totals["expected"] if totals["expected"] else 0.0
    )
    totals["f1"] = (
        2.0
        * totals["precision"]
        * totals["recall"]
        / (totals["precision"] + totals["recall"])
        if totals["precision"] + totals["recall"]
        else 0.0
    )
    return totals


def _event_state(item: Mapping[str, Any] | None, expected: Mapping[str, Any] | None) -> str:
    if expected is None:
        return "not_represented_in_gt"
    if item is None:
        return "absent"
    return "exact" if _skip(item) == _skip(expected) else "skip_mismatch"


def classify_changed_event(
    expected: Mapping[str, Any] | None,
    accepted: Mapping[str, Any] | None,
    issue274: Mapping[str, Any] | None,
) -> str:
    """Classify an accepted-vs-Issue274 semantic difference against rebased GT."""

    if expected is None:
        return "not_represented_in_gt"
    accepted_state = _event_state(accepted, expected)
    issue274_state = _event_state(issue274, expected)
    if issue274_state == "exact" and accepted_state != "exact":
        return "improvement"
    if accepted_state == "exact" and issue274_state != "exact":
        return "regression"
    return "neutral"


def _json_item(item: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"skip": _skip(item), "comment": item.get("comment")}


def _semantic_items_differ(
    accepted: Mapping[str, Any] | None, issue274: Mapping[str, Any] | None
) -> bool:
    if accepted is None or issue274 is None:
        return accepted is not issue274
    return _skip(accepted) != _skip(issue274)


def _compare_changed_page(
    *,
    page_id: str,
    rebased_expected: Any,
    accepted_payload: Any,
    issue274_payload: Any,
) -> dict[str, Any]:
    expected_by_key = _index(rebased_expected)
    accepted_by_key = _index(accepted_payload)
    issue274_by_key = _index(issue274_payload)
    differences = []
    for key in sorted(set(accepted_by_key) | set(issue274_by_key)):
        accepted, issue274 = accepted_by_key.get(key), issue274_by_key.get(key)
        if not _semantic_items_differ(accepted, issue274):
            continue
        expected = expected_by_key.get(key)
        differences.append(
            {
                "key": list(key),
                "rebased_expected": _json_item(expected),
                "accepted_issue264": _json_item(accepted),
                "issue274": _json_item(issue274),
                "accepted_state": _event_state(accepted, expected),
                "issue274_state": _event_state(issue274, expected),
                "classification": classify_changed_event(expected, accepted, issue274),
            }
        )
    return {
        "page_id": page_id,
        "rebased_expected": [
            {"key": list(key), **_json_item(item)}
            for key, item in sorted(expected_by_key.items())
        ],
        "accepted_issue264_output": [
            {"key": list(key), **_json_item(item)}
            for key, item in sorted(accepted_by_key.items())
        ],
        "issue274_output": [
            {"key": list(key), **_json_item(item)}
            for key, item in sorted(issue274_by_key.items())
        ],
        "differences": differences,
    }


def _runtime_with_explicit_allocator_names(source_report: Mapping[str, Any]) -> dict[str, Any]:
    runtime = source_report.get("runtime", {})
    if not isinstance(runtime, Mapping):
        runtime = {}
    return {
        "elapsed_sec": runtime.get("elapsed_sec"),
        "torch_cuda_max_memory_allocated": runtime.get(
            "torch_cuda_max_memory_allocated", runtime.get("max_memory_allocated")
        ),
        "torch_cuda_max_memory_reserved": runtime.get(
            "torch_cuda_max_memory_reserved", runtime.get("max_memory_reserved")
        ),
        "total_gpu_peak_measured": False,
        "total_gpu_peak_note": "Total GPU peak was not measured; source values are PyTorch CUDA allocator peaks only.",
    }


def run(
    *,
    reuse_root: Path = DEFAULT_REUSE_ROOT,
    accepted_root: Path = DEFAULT_ACCEPTED_ROOT,
    page_inputs_path: Path = DEFAULT_PAGE_INPUTS,
    output_path: Path | None = None,
) -> Path:
    source_report_path = reuse_root / "issue274_full68_mmr_reuse.json"
    source_report = _load_json(source_report_path)
    if not isinstance(source_report, Mapping):
        raise ValueError(f"Malformed Issue #274 report: {source_report_path}")
    page_inputs = _page_inputs(page_inputs_path)
    pages, mappings = [], []
    source_fixture_items = 0
    coalesced_items = 0
    changed_index_keys = 0
    changed_page_comparison = []
    changed_page_ids = []

    for global_index, page_input in enumerate(page_inputs):
        page_id = str(page_input["page_id"])
        fixture_path = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
        historical_fixture = (
            _load_json(fixture_path) if fixture_path.is_file() else {"overrides": []}
        )
        source_count = len(normalise_overrides(historical_fixture))
        source_fixture_items += source_count
        current_numbering_path = accepted_root / "intermediate" / page_id / "numbering_base.json"
        detected_path = reuse_root / "intermediate" / page_id / "overrides_mmr.json"
        accepted_path = accepted_root / "intermediate" / page_id / "overrides_mmr.json"
        for path in (current_numbering_path, detected_path, accepted_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        current_numbering = _load_json(current_numbering_path)
        detected = _load_json(detected_path)
        accepted = _load_json(accepted_path)
        page_mappings: list[dict[str, Any]] = []
        if source_count:
            historical_numbering_value = page_input.get("numbering_base")
            if not historical_numbering_value:
                raise ValueError(f"Missing historical numbering for {page_id}")
            historical_numbering = _load_json(
                _resolve_project_path(str(historical_numbering_value))
            )
            rebased_expected, page_mappings = rebase_expected_overrides(
                historical_fixture,
                historical_numbering,
                current_numbering,
                global_page_index=global_index,
            )
            for item in page_mappings:
                item["page_id"] = page_id
            mappings.extend(page_mappings)
            changed_index_keys += sum(bool(item["changed"]) for item in page_mappings)
            coalesced_items += sum(
                bool(item["coalesced_equivalent_fixture"]) for item in page_mappings
            )
        else:
            rebased_expected = {"overrides": []}
        scoring = _score(rebased_expected, detected)
        pages.append(
            {
                "page_id": page_id,
                "global_index": global_index,
                "scoring": scoring,
                "fixture_rebase": {
                    "source_fixture_items": source_count,
                    "rebased_unique_expected_events": scoring["counts"]["expected"],
                    "mapped_fixture_items": len(page_mappings),
                    "coalesced_fixture_items": sum(
                        bool(item["coalesced_equivalent_fixture"]) for item in page_mappings
                    ),
                    "changed_index_keys": sum(bool(item["changed"]) for item in page_mappings),
                    "mappings": page_mappings,
                },
            }
        )
        if _semantic_index(accepted) != _semantic_index(detected):
            changed_page_ids.append(page_id)
            changed_page_comparison.append(
                _compare_changed_page(
                    page_id=page_id,
                    rebased_expected=rebased_expected,
                    accepted_payload=accepted,
                    issue274_payload=detected,
                )
            )

    totals = _summary(pages)
    gates = {
        "page_count_68": totals["pages"] == 68,
        "historical_source_fixture_items_182": source_fixture_items == 182,
        "all_182_fixture_items_mapped": len(mappings) == 182,
        "zero_expected_pages_16": totals["zero_expected_pages"] == 16,
        "zero_expected_page_detections_zero": totals["zero_expected_page_detections"] == 0,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
    }
    report = {
        "schema_version": "issue274.full68_mmr_reuse.geometry_rebased.v2",
        "status": "passed" if all(gates.values()) else "failed",
        "evaluation_contract": {
            "historical_numbering_geometry_use": "evaluation-only fixture bbox rebase",
            "historical_numbering_as_production_input": False,
            "mmr_reexecuted": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "current_numbering_base_reused": True,
            "completed_issue274_overrides_reused": True,
        },
        "source_paths": {
            "issue274_report": str(source_report_path),
            "historical_page_inputs": str(page_inputs_path),
            "current_numbering_root": str(accepted_root / "intermediate"),
            "detected_root": str(reuse_root / "intermediate"),
            "accepted_issue264_root": str(accepted_root / "intermediate"),
        },
        "historical_source_fixture_items": source_fixture_items,
        "rebased_unique_expected_events": totals["expected"],
        "detected": totals["detected"],
        "matched_tp": totals["matched_tp"],
        "missed_fn": totals["missed_fn"],
        "skip_mismatch": totals["skip_mismatch"],
        "unexpected_fp": totals["unexpected_fp"],
        "precision": totals["precision"],
        "recall": totals["recall"],
        "f1": totals["f1"],
        "zero_expected_pages": totals["zero_expected_pages"],
        "geometry_rebased_summary": totals,
        "fixture_rebase": {
            "mapped_fixture_items": len(mappings),
            "coalesced_fixture_items": coalesced_items,
            "changed_index_keys": changed_index_keys,
            "unchanged_index_keys": len(mappings) - changed_index_keys,
            "mapping_methods": mapping_method_counts(mappings),
        },
        "accepted_diff": {
            "changed_pages": changed_page_ids,
            "exact_pages": 68 - len(changed_page_ids),
        },
        "changed_page_comparison": changed_page_comparison,
        "runtime": _runtime_with_explicit_allocator_names(source_report),
        "gates": gates,
        "pages": pages,
    }
    output_path = output_path or reuse_root / "issue274_full68_mmr_reuse_geometry_rebased.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "historical_source_fixture_items": source_fixture_items,
                "geometry_rebased_summary": totals,
                "fixture_rebase": report["fixture_rebase"],
                "accepted_diff": report["accepted_diff"],
                "gates": gates,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-root", type=Path, default=DEFAULT_REUSE_ROOT)
    parser.add_argument("--accepted-root", type=Path, default=DEFAULT_ACCEPTED_ROOT)
    parser.add_argument("--page-inputs", type=Path, default=DEFAULT_PAGE_INPUTS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = run(
        reuse_root=args.reuse_root,
        accepted_root=args.accepted_root,
        page_inputs_path=args.page_inputs,
        output_path=args.output,
    )
    return 0 if _load_json(output).get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
