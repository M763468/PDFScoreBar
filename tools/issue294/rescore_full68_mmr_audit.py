#!/usr/bin/env python3
"""Rescore an existing Issue #294 full68 MMR audit with the accepted #264 GT contract.

The original Issue #294 audit compared historical ``[page, system, measure]`` fixture
indices directly against current candidate geometry.  Those indices are not stable
when HOMR staff/system grouping changes.  Issue #264 established the production
acceptance contract: historical fixture bboxes are evaluation-only geometry and must
be spatially rebased onto the current physical numbering geometry before scoring.

This command is host-only and does not run detector, HOMR, SR, CNN, OCR, MMR, or
numbering.  It reuses the completed full68 matrix numbering signatures and the actual
MMR overrides already stored in the source audit report.
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
MODES = ("candidate_native_geometry", "frozen_A_geometry")
LABELS = ("B_b377", "C_latest")
PAGE_033_ONE_BAR_KEY = (32, 0, 0)


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


def _report_page_key(page: Mapping[str, Any]) -> tuple[str, str]:
    image = Path(str(page["image"]))
    return image.parent.name, image.stem


def _load_matrix_pages(manifest: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    pages: dict[tuple[str, str], Mapping[str, Any]] = {}
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Full68 manifest lacks completed_chunks")
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("Malformed completed chunk")
        report_path = _resolve_project_path(str(chunk["matrix_report"]))
        report = _load_json(report_path)
        report_pages = report.get("pages") if isinstance(report, Mapping) else None
        if not isinstance(report_pages, list):
            raise ValueError(f"Matrix report lacks pages: {report_path}")
        for page in report_pages:
            if not isinstance(page, Mapping):
                raise ValueError(f"Malformed matrix page: {report_path}")
            key = _report_page_key(page)
            if key in pages:
                raise RuntimeError(f"Duplicate full68 matrix page: {key}")
            pages[key] = page
    if len(pages) != 68:
        raise RuntimeError(f"Expected 68 matrix pages, got {len(pages)}")
    return pages


def _signature_to_numbering(signature: Mapping[str, Any]) -> dict[str, Any]:
    pages = signature.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Candidate numbering signature must contain exactly one page")
    systems_raw = pages[0].get("systems")
    if not isinstance(systems_raw, list):
        raise ValueError("Candidate numbering signature lacks systems")
    systems: list[dict[str, Any]] = []
    for system_index, system in enumerate(systems_raw):
        if not isinstance(system, Mapping):
            raise ValueError(f"Malformed candidate system {system_index}")
        bboxes = system.get("measure_bboxes")
        if not isinstance(bboxes, list):
            raise ValueError(f"Candidate system {system_index} lacks measure_bboxes")
        systems.append({"measures": [{"bbox": list(bbox)} for bbox in bboxes]})
    return {"pages": [{"systems": systems}]}


def _compact(payload: Any) -> list[dict[str, int]]:
    compact = [
        {key: int(item[key]) for key in ("page", "system", "measure", "skip")}
        for item in normalise_overrides(payload)
    ]
    return sorted(
        compact,
        key=lambda item: (item["page"], item["system"], item["measure"], item["skip"]),
    )


def _override_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _skip(item: Mapping[str, Any]) -> int:
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
            missed.append({"key": list(key), "expected_skip": _skip(expected_item)})
        elif _skip(expected_item) == _skip(detected_item):
            matched.append({"key": list(key), "skip": _skip(detected_item)})
        else:
            mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": _skip(expected_item),
                    "detected_skip": _skip(detected_item),
                }
            )
    for key, detected_item in detected_by_key.items():
        if key not in expected_by_key:
            unexpected.append({"key": list(key), "detected_skip": _skip(detected_item)})

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


def _row_start_equal(expected: Any, actual: Any) -> bool:
    expected_items = {
        _override_key(item): _skip(item)
        for item in normalise_overrides(expected)
        if int(item["measure"]) == 0
    }
    actual_items = {
        _override_key(item): _skip(item)
        for item in normalise_overrides(actual)
        if int(item["measure"]) == 0
    }
    return expected_items == actual_items


def _historical_expected(page_id: str) -> tuple[Any, int]:
    fixture = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
    if not fixture.is_file():
        return {"overrides": []}, 0
    payload = _load_json(fixture)
    return payload, len(normalise_overrides(payload))


def _score_condition(
    *,
    source_pages: list[Mapping[str, Any]],
    matrix_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    page_inputs: Mapping[str, Mapping[str, Any]],
    mode: str,
    label: str,
) -> dict[str, Any]:
    if len(source_pages) != 68:
        raise RuntimeError(f"Expected 68 source condition pages, got {len(source_pages)}")

    totals = {
        "pages": 68,
        "historical_source_fixture_items": 0,
        "mapped_historical_source_items": 0,
        "expected": 0,
        "detected": 0,
        "matched_tp": 0,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
        "zero_expected_pages": 0,
        "zero_expected_page_detections": 0,
    }
    pages: list[dict[str, Any]] = []
    all_mappings: list[dict[str, Any]] = []
    row_start_equal = True
    page_042_exact = False
    page_033_veto = True

    for source_page in source_pages:
        page_id = str(source_page["page_id"])
        score = str(source_page["score"])
        page_name = str(source_page["page_name"])
        global_index = int(page_id.removeprefix("page_")) - 1
        actual = source_page.get("actual", [])
        expected, source_fixture_count = _historical_expected(page_id)
        totals["historical_source_fixture_items"] += source_fixture_count

        matrix_page = matrix_pages.get((score, page_name))
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {page_id}: {(score, page_name)}")
        signature = matrix_page["modes"][mode]["variants"][label]["numbering"]
        if not isinstance(signature, Mapping):
            raise ValueError(f"Malformed numbering signature for {page_id} {mode}:{label}")
        current_numbering = _signature_to_numbering(signature)

        mappings: list[dict[str, Any]] = []
        if source_fixture_count:
            page_input = page_inputs.get(page_id)
            if page_input is None or not page_input.get("numbering_base"):
                raise ValueError(f"Missing historical numbering_base mapping for {page_id}")
            historical_path = _resolve_project_path(str(page_input["numbering_base"]))
            historical_numbering = _load_json(historical_path)
            expected, mappings = rebase_expected_overrides(
                expected,
                historical_numbering,
                current_numbering,
                global_page_index=global_index,
            )
            for mapping in mappings:
                mapping["page_id"] = page_id
            all_mappings.extend(mappings)
            totals["mapped_historical_source_items"] += len(mappings)

        scoring = _score_overrides(expected, actual)
        counts = scoring["counts"]
        for key in (
            "expected",
            "detected",
            "matched_tp",
            "missed_fn",
            "skip_mismatch",
            "unexpected_fp",
        ):
            totals[key] += int(counts[key])
        if counts["expected"] == 0:
            totals["zero_expected_pages"] += 1
            totals["zero_expected_page_detections"] += int(counts["detected"])

        row_equal = _row_start_equal(expected, actual)
        row_start_equal = row_start_equal and row_equal
        expected_compact = _compact(expected)
        actual_compact = _compact(actual)
        if page_id == "page_042":
            page_042_exact = expected_compact == actual_compact and len(expected_compact) == 5
        if page_id == "page_033":
            page_033_veto = not any(
                (item["page"], item["system"], item["measure"]) == PAGE_033_ONE_BAR_KEY
                for item in actual_compact
            )

        pages.append(
            {
                "page_id": page_id,
                "score": score,
                "page_name": page_name,
                "source_fixture_items": source_fixture_count,
                "rebased_unique_expected": counts["expected"],
                "expected": expected_compact,
                "actual": actual_compact,
                "scoring": scoring,
                "row_start_semantic_equal": row_equal,
                "fixture_rebase": {
                    "mapping_count": len(mappings),
                    "changed_key_count": sum(bool(item["changed"]) for item in mappings),
                    "coalesced_equivalent_items": sum(
                        bool(item["coalesced_equivalent_fixture"]) for item in mappings
                    ),
                    "mappings": mappings,
                },
            }
        )

    gates = {
        "page_count_68": totals["pages"] == 68,
        "historical_source_fixture_items_182": totals["historical_source_fixture_items"] == 182,
        "fixture_rebase_mapped_all_182_source_items": totals["mapped_historical_source_items"]
        == 182,
        "zero_expected_pages_scored": totals["zero_expected_pages"] == 16,
        "zero_expected_page_detections_zero": totals["zero_expected_page_detections"] == 0,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
        "row_start_semantics": row_start_equal,
        "page_033_one_bar_veto": page_033_veto,
        "page_042_five_overrides": page_042_exact,
    }
    return {
        "totals": totals,
        "gates": gates,
        "fixture_rebase": {
            "mapping_methods": mapping_method_counts(all_mappings),
            "changed_index_keys": sum(bool(item["changed"]) for item in all_mappings),
            "coalesced_equivalent_source_items": sum(
                bool(item["coalesced_equivalent_fixture"]) for item in all_mappings
            ),
        },
        "pages": pages,
    }


def run(source_report_path: Path, output_path: Path | None = None) -> Path:
    source = _load_json(source_report_path)
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Source MMR audit is not completed: {source_report_path}")
    if source.get("schema_version") != "issue294.full68_mmr_audit.v1":
        raise ValueError(f"Unexpected source MMR schema: {source.get('schema_version')}")

    manifest_path = _resolve_project_path(str(source["full68_manifest"]))
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")
    matrix_pages = _load_matrix_pages(manifest)
    page_inputs = _page_inputs(DEFAULT_PAGE_INDEX)

    conditions_raw = source.get("conditions")
    if not isinstance(conditions_raw, Mapping):
        raise ValueError("Source MMR audit lacks conditions")
    conditions: dict[str, Any] = {}
    for mode in MODES:
        for label in LABELS:
            key = f"{mode}:{label}"
            condition = conditions_raw.get(key)
            if not isinstance(condition, Mapping):
                raise ValueError(f"Source MMR audit lacks condition {key}")
            source_pages = condition.get("pages")
            if not isinstance(source_pages, list):
                raise ValueError(f"Source MMR condition lacks pages: {key}")
            conditions[key] = _score_condition(
                source_pages=source_pages,
                matrix_pages=matrix_pages,
                page_inputs=page_inputs,
                mode=mode,
                label=label,
            )

    comparisons: dict[str, Any] = {}
    for mode in MODES:
        left = conditions[f"{mode}:B_b377"]["pages"]
        right = conditions[f"{mode}:C_latest"]["pages"]
        per_page = [
            left_page["actual"] == right_page["actual"]
            for left_page, right_page in zip(left, right)
        ]
        comparisons[f"{mode}:B_vs_C"] = {
            "all_pages_exact": all(per_page),
            "different_pages": [
                left[i]["page_id"] for i, equal in enumerate(per_page) if not equal
            ],
        }

    gates = {
        "all_condition_acceptance_gates": all(
            all(condition["gates"].values()) for condition in conditions.values()
        ),
        "B_C_candidate_native_mmr_exact": comparisons["candidate_native_geometry:B_vs_C"][
            "all_pages_exact"
        ],
        "B_C_frozen_A_mmr_exact": comparisons["frozen_A_geometry:B_vs_C"]["all_pages_exact"],
    }
    payload = {
        "schema_version": "issue294.full68_mmr_geometry_rebased_score.v1",
        "status": "passed" if all(gates.values()) else "failed",
        "source_report": str(source_report_path.resolve()),
        "full68_manifest": str(manifest_path.resolve()),
        "evaluation_contract": {
            "historical_numbering_geometry_use": "evaluation-only fixture bbox rebase",
            "historical_numbering_as_production_input": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
            "numbering_reexecuted": False,
            "source_mmr_actual_overrides_reused": True,
            "source_matrix_numbering_signatures_reused": True,
        },
        "conditions": conditions,
        "comparisons": comparisons,
        "gates": gates,
    }
    if output_path is None:
        output_path = source_report_path.with_name("full68_mmr_geometry_rebased_score_01.json")
    _write_json(output_path, payload)
    print(json.dumps({"status": payload["status"], "gates": gates}, ensure_ascii=False))
    print(f"report: {output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        output = run(args.source_report, args.output)
        payload = _load_json(output)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
