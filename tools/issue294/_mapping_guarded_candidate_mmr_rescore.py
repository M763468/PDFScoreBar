#!/usr/bin/env python3
"""Implementation for the Issue #294 mapping-guarded retained MMR rescore.

The accepted Issue #264 geometry-rebase report is used as the durable GT anchor.
Retained Issue #294 actual MMR overrides are rebased from the numbering geometry
that ``run_full68_mmr_audit.py`` actually used: a fresh production
``MeasureNumberingPipeline`` reconstruction from the retained full68 inputs.

This is evaluation-only tooling. It does not rerun detector, HOMR, SR, OMR, CNN,
OCR, or MMR inference.
"""

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

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue264.phase_c_fixture_rebase import (
    MeasureRef,
    map_measure_bbox,
    mapping_method_counts,
    normalise_overrides,
    rebase_expected_overrides,
)
from tools.issue294.evaluate_connector_positive_grouping_candidate import _page_image_size
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import (
    LABELS,
    MODES,
    PAGE_033_ONE_BAR_KEY,
    _compact,
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
    _row_start_equal,
    _score_overrides,
)

ACCEPTED_REBASE_SCHEMA = "issue264.phase_c_mmr_geometry_rebased_score.v2"
ACCEPTED_REBASE_FINGERPRINT = {
    "historical_source_fixture_items": 182,
    "expected": 177,
    "detected": 174,
    "matched_tp": 168,
    "missed_fn": 3,
    "skip_mismatch": 6,
    "unexpected_fp": 0,
    "pages": 68,
    "zero_expected_pages": 16,
    "zero_expected_page_detections": 0,
    "mapped_historical_source_items": 182,
    "rebased_unique_expected_events": 177,
    "coalesced_equivalent_source_items": 5,
    "changed_index_keys": 85,
    "unchanged_index_keys": 97,
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score_to_numbering(score: Any) -> dict[str, Any]:
    pages = getattr(score, "pages", None)
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Score must contain exactly one page")
    return {
        "pages": [
            {
                "systems": [
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
                    for system in pages[0].systems
                ]
            }
        ]
    }


def _score_shape(score: Any) -> dict[str, Any]:
    pages = getattr(score, "pages", None)
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Score must contain exactly one page")
    systems = pages[0].systems
    measure_counts = [len(system.measures) for system in systems]
    return {
        "total_measures": sum(measure_counts),
        "system_staff_counts": [len(system.staves) for system in systems],
        "system_measure_counts": measure_counts,
    }


def _assert_source_numbering_shape(
    source_page: Mapping[str, Any], reconstructed: Mapping[str, Any]
) -> None:
    expected = {
        "total_measures": int(source_page.get("total_measures", -1)),
        "system_staff_counts": [int(value) for value in source_page.get("system_staff_counts", [])],
        "system_measure_counts": [
            int(value) for value in source_page.get("system_measure_counts", [])
        ],
    }
    actual = {
        "total_measures": int(reconstructed["total_measures"]),
        "system_staff_counts": [int(value) for value in reconstructed["system_staff_counts"]],
        "system_measure_counts": [int(value) for value in reconstructed["system_measure_counts"]],
    }
    if actual != expected:
        raise RuntimeError(
            "Reconstructed source MMR numbering does not match the completed audit "
            f"for {source_page.get('page_id')}: expected={expected} actual={actual}"
        )


def _run_numbering_score(
    matrix_page: Mapping[str, Any],
    *,
    mode: str,
    label: str,
    page_number: int,
    pipeline: Any,
) -> Any:
    variant = matrix_page["modes"][mode]["variants"][label]
    support = _load_json(_resolve_project_path(str(matrix_page["fixed_inputs"]["support_result"])))
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    return pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": _page_image_size(matrix_page),
                "page_number": page_number,
                "connector_mask_paths": {
                    "symbols": str(_resolve_project_path(str(support["connector_symbols"]))),
                    "brace_dot": str(_resolve_project_path(str(support["connector_brace_dot"]))),
                },
            }
        ]
    )


def _source_mmr_numbering(
    matrix_page: Mapping[str, Any],
    *,
    mode: str,
    label: str,
    page_number: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    score = _run_numbering_score(
        matrix_page,
        mode=mode,
        label=label,
        page_number=page_number,
        pipeline=MeasureNumberingPipeline(),
    )
    return _score_to_numbering(score), _score_shape(score)


def _candidate_numbering(
    matrix_page: Mapping[str, Any],
    *,
    mode: str,
    label: str,
    page_number: int,
) -> tuple[dict[str, Any], str]:
    pipeline = MappingGuardedConnectorPositivePipeline()
    score = _run_numbering_score(
        matrix_page,
        mode=mode,
        label=label,
        page_number=page_number,
        pipeline=pipeline,
    )
    return _score_to_numbering(score), pipeline.last_evidence_geometry_mode


def _override_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _skip(item: Mapping[str, Any]) -> int:
    return int(item.get("skip") or 0)


def _accepted_rebase_pages(
    accepted_rebase_report_path: Path,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    payload = _load_json(accepted_rebase_report_path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Malformed accepted rebase report: {accepted_rebase_report_path}")
    if payload.get("schema") != ACCEPTED_REBASE_SCHEMA:
        raise ValueError(f"Unexpected accepted rebase schema: {payload.get('schema')}")
    if payload.get("status") != "passed":
        raise ValueError("Accepted rebase report is not passed")

    summary = payload.get("geometry_rebased_summary")
    fixture_rebase = payload.get("fixture_rebase")
    gates = payload.get("gates")
    raw_pages = payload.get("pages")
    if not isinstance(summary, Mapping) or not isinstance(fixture_rebase, Mapping):
        raise ValueError("Accepted rebase report lacks summary")
    if not isinstance(gates, Mapping) or not all(bool(value) for value in gates.values()):
        raise ValueError("Accepted rebase report has a failed gate")
    if not isinstance(raw_pages, list) or len(raw_pages) != 68:
        raise ValueError("Accepted rebase report must contain 68 pages")

    actual_fingerprint = {
        "historical_source_fixture_items": int(payload.get("historical_source_fixture_items") or 0),
        "expected": int(summary.get("expected") or 0),
        "detected": int(summary.get("detected") or 0),
        "matched_tp": int(summary.get("matched_tp") or 0),
        "missed_fn": int(summary.get("missed_fn") or 0),
        "skip_mismatch": int(summary.get("skip_mismatch") or 0),
        "unexpected_fp": int(summary.get("unexpected_fp") or 0),
        "pages": int(summary.get("pages") or 0),
        "zero_expected_pages": int(summary.get("zero_expected_pages") or 0),
        "zero_expected_page_detections": int(summary.get("zero_expected_page_detections") or 0),
        "mapped_historical_source_items": int(
            fixture_rebase.get("mapped_historical_source_items") or 0
        ),
        "rebased_unique_expected_events": int(
            fixture_rebase.get("rebased_unique_expected_events") or 0
        ),
        "coalesced_equivalent_source_items": int(
            fixture_rebase.get("coalesced_equivalent_source_items") or 0
        ),
        "changed_index_keys": int(fixture_rebase.get("changed_index_keys") or 0),
        "unchanged_index_keys": int(fixture_rebase.get("unchanged_index_keys") or 0),
    }
    if actual_fingerprint != ACCEPTED_REBASE_FINGERPRINT:
        raise ValueError(
            "Accepted rebase report does not match the canonical Issue #264 "
            f"fingerprint: {actual_fingerprint}"
        )

    pages: dict[str, Mapping[str, Any]] = {}
    source_items = 0
    mapping_items = 0
    rebased_unique = 0
    coalesced = 0
    for page in raw_pages:
        if not isinstance(page, Mapping):
            raise ValueError("Malformed accepted rebase page")
        page_id = str(page.get("page_id", ""))
        if not page_id or page_id in pages:
            raise ValueError(f"Duplicate/missing accepted rebase page_id: {page_id!r}")
        page_rebase = page.get("fixture_rebase")
        if not isinstance(page_rebase, Mapping):
            raise ValueError(f"Accepted rebase page lacks fixture_rebase: {page_id}")
        mappings = page_rebase.get("mappings")
        if not isinstance(mappings, list):
            raise ValueError(f"Accepted rebase page lacks mappings: {page_id}")
        source_items += int(page_rebase.get("source_fixture_items") or 0)
        mapping_items += len(mappings)
        rebased_unique += int(page_rebase.get("rebased_unique_expected") or 0)
        coalesced += int(page_rebase.get("coalesced_equivalent_items") or 0)
        pages[page_id] = page

    if (source_items, mapping_items, rebased_unique, coalesced) != (182, 182, 177, 5):
        raise ValueError(
            "Accepted rebase page-level totals do not match canonical Issue #264 "
            f"totals: {(source_items, mapping_items, rebased_unique, coalesced)}"
        )

    provenance = {
        "path": str(accepted_rebase_report_path),
        "sha256": _sha256_file(accepted_rebase_report_path),
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "source_git_head": payload.get("source_git_head"),
        "fingerprint": actual_fingerprint,
    }
    return pages, provenance


def _rebase_accepted_expected_to_candidate(
    accepted_page: Mapping[str, Any],
    candidate_numbering: Mapping[str, Any],
    *,
    global_page_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    page_rebase = accepted_page.get("fixture_rebase")
    if not isinstance(page_rebase, Mapping):
        raise ValueError("Accepted page lacks fixture_rebase")
    anchors = page_rebase.get("mappings")
    if not isinstance(anchors, list):
        raise ValueError("Accepted page lacks mappings")

    rebased_by_key: dict[tuple[int, int, int], dict[str, Any]] = {}
    source_key_by_candidate_key: dict[tuple[int, int, int], list[int]] = {}
    mappings: list[dict[str, Any]] = []
    for anchor in anchors:
        if not isinstance(anchor, Mapping):
            raise ValueError("Malformed accepted fixture mapping")
        accepted_key_raw = anchor.get("current_key")
        historical_key_raw = anchor.get("historical_key")
        accepted_bbox_raw = anchor.get("current_bbox")
        if not isinstance(accepted_key_raw, list) or len(accepted_key_raw) != 3:
            raise ValueError(f"Malformed accepted current_key: {accepted_key_raw!r}")
        if not isinstance(historical_key_raw, list) or len(historical_key_raw) != 3:
            raise ValueError(f"Malformed accepted historical_key: {historical_key_raw!r}")
        if not isinstance(accepted_bbox_raw, list) or len(accepted_bbox_raw) != 4:
            raise ValueError(f"Malformed accepted current_bbox: {accepted_bbox_raw!r}")
        if int(accepted_key_raw[0]) != global_page_index:
            raise ValueError(
                f"Accepted mapping page mismatch: expected={global_page_index} "
                f"actual={accepted_key_raw[0]}"
            )

        accepted_ref = MeasureRef(
            system=int(accepted_key_raw[1]),
            measure=int(accepted_key_raw[2]),
            bbox=tuple(float(value) for value in accepted_bbox_raw),
        )
        candidate_ref, detail = map_measure_bbox(accepted_ref, candidate_numbering)
        candidate_key = (
            global_page_index,
            candidate_ref.system,
            candidate_ref.measure,
        )
        mapped = {
            "page": global_page_index,
            "system": candidate_ref.system,
            "measure": candidate_ref.measure,
            "skip": _skip(anchor),
        }

        existing = rebased_by_key.get(candidate_key)
        candidate_coalesced = existing is not None
        if existing is not None and _skip(existing) != _skip(mapped):
            raise ValueError(
                "Conflicting accepted Issue #264 anchors map to candidate key "
                f"{candidate_key}: existing skip={_skip(existing)} "
                f"incoming skip={_skip(mapped)}"
            )
        if existing is None:
            rebased_by_key[candidate_key] = mapped
            source_key_by_candidate_key[candidate_key] = [
                int(value) for value in historical_key_raw
            ]

        method = (
            str(detail["method"]).replace("historical", "accepted").replace("current", "candidate")
        )
        mappings.append(
            {
                "source_historical_key": [int(value) for value in historical_key_raw],
                "accepted_key": [int(value) for value in accepted_key_raw],
                "candidate_key": list(candidate_key),
                "changed_from_accepted": [
                    int(accepted_key_raw[1]),
                    int(accepted_key_raw[2]),
                ]
                != [candidate_ref.system, candidate_ref.measure],
                "accepted_source_coalesced": bool(anchor.get("coalesced_equivalent_fixture")),
                "candidate_coalesced": candidate_coalesced,
                "candidate_coalesced_with_historical_key": (
                    source_key_by_candidate_key[candidate_key] if candidate_coalesced else None
                ),
                "skip": _skip(mapped),
                "method": method,
                "overlap_score": float(detail["overlap_score"]),
                "accepted_bbox": [float(value) for value in accepted_bbox_raw],
                "candidate_bbox": list(candidate_ref.bbox),
            }
        )

    return {"overrides": list(rebased_by_key.values())}, mappings


def _candidate_condition(
    *,
    source_pages: list[Mapping[str, Any]],
    matrix_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    accepted_rebase_pages: Mapping[str, Mapping[str, Any]],
    mode: str,
    label: str,
) -> dict[str, Any]:
    totals = {
        "pages": 68,
        "source_numbering_reconstruction_exact_pages": 0,
        "accepted_source_fixture_items": 0,
        "mapped_accepted_source_items": 0,
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

        accepted_page = accepted_rebase_pages.get(page_id)
        if accepted_page is None:
            raise ValueError(f"Accepted Issue #264 rebase lacks {page_id}")
        if int(accepted_page.get("global_index", -1)) != global_index:
            raise ValueError(f"Accepted Issue #264 global index mismatch for {page_id}")

        source_numbering, source_shape = _source_mmr_numbering(
            matrix_page,
            mode=mode,
            label=label,
            page_number=global_index + 1,
        )
        _assert_source_numbering_shape(source_page, source_shape)
        totals["source_numbering_reconstruction_exact_pages"] += 1

        candidate_numbering, mapping_mode = _candidate_numbering(
            matrix_page,
            mode=mode,
            label=label,
            page_number=global_index + 1,
        )

        page_rebase = accepted_page["fixture_rebase"]
        source_fixture_count = int(page_rebase.get("source_fixture_items") or 0)
        totals["accepted_source_fixture_items"] += source_fixture_count
        expected, expected_mappings = _rebase_accepted_expected_to_candidate(
            accepted_page,
            candidate_numbering,
            global_page_index=global_index,
        )
        totals["mapped_accepted_source_items"] += len(expected_mappings)
        for item in expected_mappings:
            item["page_id"] = page_id
        expected_mappings_all.extend(expected_mappings)

        retained_actual = source_page.get("actual", [])
        actual_source_count = len(normalise_overrides(retained_actual))
        totals["retained_actual_items"] += actual_source_count
        actual_mappings: list[dict[str, Any]] = []
        actual = {"overrides": []}
        if actual_source_count:
            actual, actual_mappings = rebase_expected_overrides(
                retained_actual,
                source_numbering,
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
                "source_numbering_shape": source_shape,
                "source_fixture_items": source_fixture_count,
                "retained_actual_items": actual_source_count,
                "expected": expected_compact,
                "actual_rebased": actual_compact,
                "scoring": scoring,
                "row_start_semantic_equal": row_equal,
                "expected_rebase": {
                    "mapping_count": len(expected_mappings),
                    "changed_key_count": sum(
                        bool(item["changed_from_accepted"]) for item in expected_mappings
                    ),
                    "candidate_coalesced_items": sum(
                        bool(item["candidate_coalesced"]) for item in expected_mappings
                    ),
                },
                "actual_rebase": {
                    "source_geometry": "reconstructed_run_full68_mmr_audit_numbering",
                    "mapping_count": len(actual_mappings),
                    "changed_key_count": sum(bool(item["changed"]) for item in actual_mappings),
                },
            }
        )

    gates = {
        "page_count_68": totals["pages"] == 68,
        "source_numbering_reconstruction_exact_68": totals[
            "source_numbering_reconstruction_exact_pages"
        ]
        == 68,
        "accepted_source_fixture_items_182": totals["accepted_source_fixture_items"] == 182,
        "accepted_rebase_mapped_all_182_source_items": totals["mapped_accepted_source_items"]
        == 182,
        "retained_actual_rebase_mapped_all_items": totals["mapped_retained_actual_items"]
        == totals["retained_actual_items"],
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
            "changed_index_keys_from_issue264_accepted": sum(
                bool(item["changed_from_accepted"]) for item in expected_mappings_all
            ),
            "candidate_coalesced_items": sum(
                bool(item["candidate_coalesced"]) for item in expected_mappings_all
            ),
        },
        "actual_rebase": {
            "source_geometry": "reconstructed_run_full68_mmr_audit_numbering",
            "mapping_methods": mapping_method_counts(actual_mappings_all),
            "changed_index_keys": sum(bool(item["changed"]) for item in actual_mappings_all),
        },
        "pages": pages,
    }


def run(
    source_report_path: Path,
    accepted_rebase_report_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = _load_json(source_report_path)
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Source MMR audit is not completed: {source_report_path}")
    if source.get("schema_version") != "issue294.full68_mmr_audit.v1":
        raise ValueError(f"Unexpected source MMR schema: {source.get('schema_version')}")

    manifest = _load_json(_resolve_project_path(str(source["full68_manifest"])))
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    matrix_pages = _load_matrix_pages(manifest)
    accepted_pages, accepted_provenance = _accepted_rebase_pages(accepted_rebase_report_path)
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
                accepted_rebase_pages=accepted_pages,
                mode=mode,
                label=label,
            )

    bc_exact_by_mode: dict[str, bool] = {}
    for mode in MODES:
        left = conditions[f"{mode}:B_b377"]["pages"]
        right = conditions[f"{mode}:C_latest"]["pages"]
        bc_exact_by_mode[mode] = all(
            left_page["page_id"] == right_page["page_id"]
            and left_page["actual_rebased"] == right_page["actual_rebased"]
            for left_page, right_page in zip(left, right)
        )

    all_condition_gates = all(
        all(bool(value) for value in condition["gates"].values())
        for condition in conditions.values()
    )
    payload = {
        "schema_version": "issue294.mapping_guarded_candidate_mmr_rescore.v3",
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
            "historical_issue120_numbering_required": False,
            "issue264_accepted_rebase_report_reused": True,
            "source_mmr_numbering_reconstructed_with_production_pipeline": True,
            "source_mmr_numbering_shape_verified_against_completed_audit": True,
            "issue264_accepted_physical_gt_rebased_to_candidate_geometry": True,
            "retained_actual_overrides_rebased_from_source_mmr_geometry_to_candidate": True,
        },
        "source_report": str(source_report_path),
        "accepted_issue264_rebase_report": accepted_provenance,
        "conditions": conditions,
        "B_C_actual_rebased_exact_by_mode": bc_exact_by_mode,
        "all_condition_acceptance_gates": all_condition_gates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-report",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_mmr_audit_01.json",
    )
    parser.add_argument(
        "--accepted-rebase-report",
        type=Path,
        required=True,
        help="Accepted Issue #264 phase_c_mmr_geometry_rebased_score_report.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_candidate_mmr_rescore_01.json",
    )
    args = parser.parse_args()
    payload = run(args.source_report, args.accepted_rebase_report, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "accepted_issue264_rebase_sha256": payload["accepted_issue264_rebase_report"][
                    "sha256"
                ],
                "B_C_actual_rebased_exact_by_mode": payload["B_C_actual_rebased_exact_by_mode"],
                "all_condition_acceptance_gates": payload["all_condition_acceptance_gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0
