#!/usr/bin/env python3
"""Retained-only MMR rescore for the Issue #294 mapping-guarded grouping candidate.

The source full68 MMR audit was produced against the retained/current numbering
geometry. This tool reconstructs the experiment-only mapping-guarded grouping
candidate, then spatially rebases both:

* historical expected MMR fixtures -> candidate numbering geometry; and
* retained actual MMR overrides -> candidate numbering geometry.

The second rebase is required because [page, system, measure] indices can shift when
system grouping changes (notably page_052). No detector, HOMR, SR, OMR, CNN, OCR, or
MMR inference is rerun.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue264.phase_c_fixture_rebase import (
    mapping_method_counts,
    normalise_overrides,
    rebase_expected_overrides,
)
from tools.issue294.evaluate_connector_positive_grouping_candidate import _page_image_size
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import (
    DEFAULT_PAGE_INDEX,
    LABELS,
    MODES,
    PAGE_033_ONE_BAR_KEY,
    _compact,
    _historical_expected,
    _load_json,
    _load_matrix_pages,
    _page_inputs,
    _resolve_project_path,
    _row_start_equal,
    _score_overrides,
    _signature_to_numbering,
)


def _score_to_numbering(score: Any) -> dict[str, Any]:
    pages = getattr(score, "pages", None)
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Candidate score must contain exactly one page")
    systems: list[dict[str, Any]] = []
    for system in pages[0].systems:
        systems.append(
            {
                "measures": [
                    {
                        "bbox": [
                            int(measure.bbox.x1),
                            int(measure.bbox.y1),
                            int(measure.bbox.x2),
                            int(measure.bbox.y2),
                        ]
                    }
                    for measure in system.measures
                ]
            }
        )
    return {"pages": [{"systems": systems}]}


def _candidate_numbering(
    matrix_page: Mapping[str, Any], *, mode: str, label: str
) -> tuple[dict[str, Any], str]:
    variant = matrix_page["modes"][mode]["variants"][label]
    support = _load_json(
        _resolve_project_path(str(matrix_page["fixed_inputs"]["support_result"]))
    )
    pipeline = MappingGuardedConnectorPositivePipeline()
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    score = pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": _page_image_size(matrix_page),
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(
                        _resolve_project_path(str(support["connector_symbols"]))
                    ),
                    "brace_dot": str(
                        _resolve_project_path(str(support["connector_brace_dot"]))
                    ),
                },
            }
        ]
    )
    return _score_to_numbering(score), pipeline.last_evidence_geometry_mode


def _override_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _candidate_condition(
    *,
    source_pages: list[Mapping[str, Any]],
    matrix_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    page_inputs: Mapping[str, Mapping[str, Any]],
    mode: str,
    label: str,
) -> dict[str, Any]:
    totals = {
        "pages": 68,
        "historical_source_fixture_items": 0,
        "mapped_historical_source_items": 0,
        "retained_actual_items": 0,
        "mapped_retained_actual_items": 0,
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
    expected_mappings_all: list[dict[str, Any]] = []
    actual_mappings_all: list[dict[str, Any]] = []
    row_start_equal = True
    page_042_exact = False
    page_033_veto = True

    if len(source_pages) != 68:
        raise RuntimeError(f"Expected 68 source pages, got {len(source_pages)}")

    for source_page in source_pages:
        page_id = str(source_page["page_id"])
        score_name = str(source_page["score"])
        page_name = str(source_page["page_name"])
        global_index = int(page_id.removeprefix("page_")) - 1
        matrix_page = matrix_pages.get((score_name, page_name))
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {page_id}: {(score_name, page_name)}")

        variant = matrix_page["modes"][mode]["variants"][label]
        retained_numbering = _signature_to_numbering(variant["numbering"])
        candidate_numbering, mapping_mode = _candidate_numbering(
            matrix_page,
            mode=mode,
            label=label,
        )

        expected, source_fixture_count = _historical_expected(page_id)
        totals["historical_source_fixture_items"] += source_fixture_count
        expected_mappings: list[dict[str, Any]] = []
        if source_fixture_count:
            page_input = page_inputs.get(page_id)
            if page_input is None or not page_input.get("numbering_base"):
                raise ValueError(f"Missing historical numbering_base mapping for {page_id}")
            historical_numbering = _load_json(
                _resolve_project_path(str(page_input["numbering_base"]))
            )
            expected, expected_mappings = rebase_expected_overrides(
                expected,
                historical_numbering,
                candidate_numbering,
                global_page_index=global_index,
            )
            for item in expected_mappings:
                item["page_id"] = page_id
            totals["mapped_historical_source_items"] += len(expected_mappings)
            expected_mappings_all.extend(expected_mappings)

        retained_actual = source_page.get("actual", [])
        actual_source_count = len(normalise_overrides(retained_actual))
        totals["retained_actual_items"] += actual_source_count
        actual_mappings: list[dict[str, Any]] = []
        actual = {"overrides": []}
        if actual_source_count:
            actual, actual_mappings = rebase_expected_overrides(
                retained_actual,
                retained_numbering,
                candidate_numbering,
                global_page_index=global_index,
            )
            for item in actual_mappings:
                item["page_id"] = page_id
            totals["mapped_retained_actual_items"] += len(actual_mappings)
            actual_mappings_all.extend(actual_mappings)

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
                _override_key(item) == PAGE_033_ONE_BAR_KEY for item in actual_compact
            )

        pages.append(
            {
                "page_id": page_id,
                "score": score_name,
                "page_name": page_name,
                "mapping_mode": mapping_mode,
                "source_fixture_items": source_fixture_count,
                "retained_actual_items": actual_source_count,
                "expected": expected_compact,
                "actual_rebased": actual_compact,
                "scoring": scoring,
                "row_start_semantic_equal": row_equal,
                "expected_rebase": {
                    "mapping_count": len(expected_mappings),
                    "changed_key_count": sum(bool(item["changed"]) for item in expected_mappings),
                },
                "actual_rebase": {
                    "mapping_count": len(actual_mappings),
                    "changed_key_count": sum(bool(item["changed"]) for item in actual_mappings),
                },
            }
        )

    gates = {
        "page_count_68": totals["pages"] == 68,
        "historical_source_fixture_items_182": totals["historical_source_fixture_items"] == 182,
        "fixture_rebase_mapped_all_182_source_items": totals["mapped_historical_source_items"] == 182,
        "retained_actual_rebase_mapped_all_items": totals["mapped_retained_actual_items"] == totals["retained_actual_items"],
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
        "expected_rebase": {
            "mapping_methods": mapping_method_counts(expected_mappings_all),
            "changed_index_keys": sum(bool(item["changed"]) for item in expected_mappings_all),
        },
        "actual_rebase": {
            "mapping_methods": mapping_method_counts(actual_mappings_all),
            "changed_index_keys": sum(bool(item["changed"]) for item in actual_mappings_all),
        },
        "pages": pages,
    }


def run(source_report_path: Path, output_path: Path) -> dict[str, Any]:
    source = _load_json(source_report_path)
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Source MMR audit is not completed: {source_report_path}")
    if source.get("schema_version") != "issue294.full68_mmr_audit.v1":
        raise ValueError(f"Unexpected source MMR schema: {source.get('schema_version')}")

    manifest = _load_json(_resolve_project_path(str(source["full68_manifest"])))
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    matrix_pages = _load_matrix_pages(manifest)
    page_inputs = _page_inputs(DEFAULT_PAGE_INDEX)
    conditions_raw = source.get("conditions")
    if not isinstance(conditions_raw, Mapping):
        raise ValueError("Source MMR audit lacks conditions")

    conditions: dict[str, Any] = {}
    for mode in MODES:
        for label in LABELS:
            key = f"{mode}:{label}"
            source_condition = conditions_raw.get(key)
            if not isinstance(source_condition, Mapping):
                raise ValueError(f"Source MMR audit lacks condition {key}")
            source_pages = source_condition.get("pages")
            if not isinstance(source_pages, list):
                raise ValueError(f"Source MMR condition lacks pages: {key}")
            conditions[key] = _candidate_condition(
                source_pages=source_pages,
                matrix_pages=matrix_pages,
                page_inputs=page_inputs,
                mode=mode,
                label=label,
            )

    bc_exact_by_mode: dict[str, bool] = {}
    for mode in MODES:
        left = conditions[f"{mode}:B_b377"]["pages"]
        right = conditions[f"{mode}:C_latest"]["pages"]
        bc_exact_by_mode[mode] = all(
            l["page_id"] == r["page_id"] and l["actual_rebased"] == r["actual_rebased"]
            for l, r in zip(left, right)
        )

    all_condition_gates = all(
        all(bool(value) for value in condition["gates"].values())
        for condition in conditions.values()
    )
    payload = {
        "schema_version": "issue294.mapping_guarded_candidate_mmr_rescore.v1",
        "status": "completed",
        "execution_contract": {
            "retained_artifacts_only": True,
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
            "numbering_reconstructed": True,
            "historical_fixture_rebased_to_candidate_geometry": True,
            "retained_actual_overrides_rebased_to_candidate_geometry": True,
        },
        "source_report": str(source_report_path),
        "conditions": conditions,
        "B_C_actual_rebased_exact_by_mode": bc_exact_by_mode,
        "all_condition_acceptance_gates": all_condition_gates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-report",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_mmr_audit_01.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_candidate_mmr_rescore_01.json",
    )
    args = parser.parse_args()
    payload = run(args.source_report, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "B_C_actual_rebased_exact_by_mode": payload[
                    "B_C_actual_rebased_exact_by_mode"
                ],
                "all_condition_acceptance_gates": payload[
                    "all_condition_acceptance_gates"
                ],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
