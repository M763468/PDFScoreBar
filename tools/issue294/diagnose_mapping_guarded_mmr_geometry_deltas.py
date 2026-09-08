#!/usr/bin/env python3
"""Diagnose retained MMR deltas caused by Issue #294 candidate geometry.

This experiment-only tool does not rerun detector, HOMR, SR, OMR, CNN, OCR, or
MMR inference.  It reconstructs only the mapping-guarded numbering geometry for
candidate-native and frozen-A modes, rebuilds the deterministic MMR support views,
and compares those bboxes at keys whose already-retained MMR overrides differ.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.serialization import score_to_dict
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue294.evaluate_connector_positive_grouping_candidate import _page_image_size
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import (
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
)

MODES = ("candidate_native_geometry", "frozen_A_geometry")
LABELS = ("B_b377", "C_latest")
VIEWS = ("primary", "implicit_start_alternate", "fallback")


def _key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _compact_map(items: Any) -> dict[tuple[int, int, int], int]:
    if not isinstance(items, list):
        return {}
    return {_key(item): int(item.get("skip") or 0) for item in items if isinstance(item, Mapping)}


def differing_override_keys(
    left: Any, right: Any
) -> list[tuple[int, int, int]]:
    """Return sorted semantic keys whose retained override presence/value differs."""

    left_map = _compact_map(left)
    right_map = _compact_map(right)
    return sorted(
        key for key in set(left_map) | set(right_map) if left_map.get(key) != right_map.get(key)
    )


def bbox_delta(frozen: list[int], native: list[int]) -> dict[str, Any]:
    """Describe candidate-native bbox movement relative to frozen-A."""

    if len(frozen) != 4 or len(native) != 4:
        raise ValueError("bbox_delta requires four-value boxes")
    fx1, fy1, fx2, fy2 = (float(value) for value in frozen)
    nx1, ny1, nx2, ny2 = (float(value) for value in native)
    inter_w = max(0.0, min(fx2, nx2) - max(fx1, nx1))
    inter_h = max(0.0, min(fy2, ny2) - max(fy1, ny1))
    inter = inter_w * inter_h
    f_area = max(0.0, fx2 - fx1) * max(0.0, fy2 - fy1)
    n_area = max(0.0, nx2 - nx1) * max(0.0, ny2 - ny1)
    union = f_area + n_area - inter
    fcx, fcy = (fx1 + fx2) / 2.0, (fy1 + fy2) / 2.0
    ncx, ncy = (nx1 + nx2) / 2.0, (ny1 + ny2) / 2.0
    edges = [nx1 - fx1, ny1 - fy1, nx2 - fx2, ny2 - fy2]
    return {
        "equal": all(math.isclose(value, 0.0, abs_tol=1e-9) for value in edges),
        "native_minus_frozen_edges": edges,
        "native_minus_frozen_size": [
            (nx2 - nx1) - (fx2 - fx1),
            (ny2 - ny1) - (fy2 - fy1),
        ],
        "center_delta": [ncx - fcx, ncy - fcy],
        "center_distance": math.hypot(ncx - fcx, ncy - fcy),
        "iou": inter / union if union > 0 else 1.0,
        "horizontal_changed": not (math.isclose(nx1, fx1) and math.isclose(nx2, fx2)),
        "vertical_changed": not (math.isclose(ny1, fy1) and math.isclose(ny2, fy2)),
    }


def _numbering(
    matrix_page: Mapping[str, Any], *, mode: str, label: str, page_number: int
) -> tuple[dict[str, Any], str]:
    variant = matrix_page["modes"][mode]["variants"][label]
    fixed = _load_json(
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
                "page_number": page_number,
                "connector_mask_paths": {
                    "symbols": str(_resolve_project_path(str(fixed["connector_symbols"]))),
                    "brace_dot": str(_resolve_project_path(str(fixed["connector_brace_dot"]))),
                },
            }
        ]
    )
    return score_to_dict(score), pipeline.last_evidence_geometry_mode


def _measure_snapshot(numbering: Mapping[str, Any], support: Mapping[str, Any], key: tuple[int, int, int]) -> dict[str, Any]:
    _page, system_index, measure_index = key
    page = numbering["pages"][0]
    systems = page.get("systems", [])
    if system_index >= len(systems):
        return {"present": False, "reason": "system_absent"}
    system = systems[system_index]
    measures = system.get("measures", [])
    if measure_index >= len(measures):
        return {"present": False, "reason": "measure_absent"}

    result: dict[str, Any] = {
        "present": True,
        "base_measure_bbox": [int(value) for value in measures[measure_index]["bbox"]],
        "base_system_staff_bboxes": [
            [int(value) for value in staff["bbox"]] for staff in system.get("staves", [])
        ],
        "views": {},
    }
    for view_name in VIEWS:
        view_system = support["views"][view_name]["pages"][0]["systems"][system_index]
        result["views"][view_name] = {
            "measure_bbox": [
                int(value) for value in view_system["measures"][measure_index]["bbox"]
            ],
            "staff_bboxes": [
                [int(value) for value in staff["bbox"]]
                for staff in view_system.get("staves", [])
            ],
        }
    return result


def _snapshot_delta(frozen: Mapping[str, Any], native: Mapping[str, Any]) -> dict[str, Any]:
    if not frozen.get("present") or not native.get("present"):
        return {
            "comparable": False,
            "frozen_present": bool(frozen.get("present")),
            "native_present": bool(native.get("present")),
        }
    view_deltas = {
        view_name: bbox_delta(
            list(frozen["views"][view_name]["measure_bbox"]),
            list(native["views"][view_name]["measure_bbox"]),
        )
        for view_name in VIEWS
    }
    return {
        "comparable": True,
        "base_measure": bbox_delta(
            list(frozen["base_measure_bbox"]), list(native["base_measure_bbox"])
        ),
        "views": view_deltas,
        "any_measure_geometry_changed": any(
            not item["equal"] for item in [
                bbox_delta(
                    list(frozen["base_measure_bbox"]), list(native["base_measure_bbox"])
                ),
                *view_deltas.values(),
            ]
        ),
        "primary_horizontal_changed": view_deltas["primary"]["horizontal_changed"],
        "primary_vertical_changed": view_deltas["primary"]["vertical_changed"],
    }


def _condition_pages(rescore: Mapping[str, Any], mode: str, label: str) -> dict[str, Mapping[str, Any]]:
    condition = rescore["conditions"][f"{mode}:{label}"]
    return {str(page["page_id"]): page for page in condition["pages"]}


def run(manifest_path: Path, rescore_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    rescore = _load_json(rescore_path)
    if not isinstance(rescore, Mapping) or rescore.get("status") != "completed":
        raise ValueError("Mapping-guarded MMR rescore is not completed")
    matrix_pages = _load_matrix_pages(manifest)

    labels: dict[str, Any] = {}
    all_differing_page_sets: list[list[str]] = []
    b_geometry: dict[str, Any] = {}
    c_geometry: dict[str, Any] = {}

    for label in LABELS:
        native_pages = _condition_pages(rescore, "candidate_native_geometry", label)
        frozen_pages = _condition_pages(rescore, "frozen_A_geometry", label)
        if set(native_pages) != set(frozen_pages) or len(native_pages) != 68:
            raise RuntimeError(f"Incomplete condition page set for {label}")
        differing_pages = [
            page_id
            for page_id in sorted(native_pages)
            if differing_override_keys(
                native_pages[page_id]["actual_rebased"], frozen_pages[page_id]["actual_rebased"]
            )
        ]
        all_differing_page_sets.append(differing_pages)
        page_records: list[dict[str, Any]] = []

        for page_id in differing_pages:
            native_page = native_pages[page_id]
            frozen_page = frozen_pages[page_id]
            matrix_key = (str(native_page["score"]), str(native_page["page_name"]))
            matrix_page = matrix_pages.get(matrix_key)
            if matrix_page is None:
                raise RuntimeError(f"Full68 matrix lacks {page_id}: {matrix_key}")
            global_index = int(page_id.removeprefix("page_")) - 1
            fixed = _load_json(
                _resolve_project_path(str(matrix_page["fixed_inputs"]["support_result"]))
            )
            current_staff_mask = _resolve_project_path(str(fixed["current_homr_staff_mask"]))

            geometries: dict[str, Any] = {}
            for mode in MODES:
                numbering, evidence_mode = _numbering(
                    matrix_page,
                    mode=mode,
                    label=label,
                    page_number=global_index + 1,
                )
                support = build_mmr_support_data(numbering, current_staff_mask)
                geometries[mode] = {
                    "numbering": numbering,
                    "support": support,
                    "connector_evidence_geometry_mode": evidence_mode,
                }

            keys = differing_override_keys(
                native_page["actual_rebased"], frozen_page["actual_rebased"]
            )
            expected_native = _compact_map(native_page["expected"])
            expected_frozen = _compact_map(frozen_page["expected"])
            actual_native = _compact_map(native_page["actual_rebased"])
            actual_frozen = _compact_map(frozen_page["actual_rebased"])
            key_records = []
            for key in keys:
                frozen_snapshot = _measure_snapshot(
                    geometries["frozen_A_geometry"]["numbering"],
                    geometries["frozen_A_geometry"]["support"],
                    key,
                )
                native_snapshot = _measure_snapshot(
                    geometries["candidate_native_geometry"]["numbering"],
                    geometries["candidate_native_geometry"]["support"],
                    key,
                )
                key_records.append(
                    {
                        "key": list(key),
                        "expected": {
                            "frozen_A_geometry": expected_frozen.get(key),
                            "candidate_native_geometry": expected_native.get(key),
                        },
                        "retained_actual": {
                            "frozen_A_geometry": actual_frozen.get(key),
                            "candidate_native_geometry": actual_native.get(key),
                        },
                        "frozen_A_geometry": frozen_snapshot,
                        "candidate_native_geometry": native_snapshot,
                        "geometry_delta_native_minus_frozen": _snapshot_delta(
                            frozen_snapshot, native_snapshot
                        ),
                    }
                )

            record = {
                "page_id": page_id,
                "score": native_page["score"],
                "page_name": native_page["page_name"],
                "differing_keys": [list(key) for key in keys],
                "candidate_native_mapping_mode": geometries["candidate_native_geometry"][
                    "connector_evidence_geometry_mode"
                ],
                "frozen_A_mapping_mode": geometries["frozen_A_geometry"][
                    "connector_evidence_geometry_mode"
                ],
                "keys": key_records,
            }
            page_records.append(record)
            target = b_geometry if label == "B_b377" else c_geometry
            target[page_id] = record

        labels[label] = {
            "differing_pages": differing_pages,
            "differing_page_count": len(differing_pages),
            "pages": page_records,
        }

    bc_page_sets_equal = all_differing_page_sets[0] == all_differing_page_sets[1]
    bc_geometry_exact = b_geometry == c_geometry
    report = {
        "schema_version": "issue294.mapping_guarded_mmr_geometry_delta_diagnostic.v1",
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
            "mmr_support_views_rebuilt_deterministically": True,
        },
        "source_manifest": str(manifest_path),
        "source_rescore": str(rescore_path),
        "labels": labels,
        "B_C_differing_page_sets_equal": bc_page_sets_equal,
        "B_C_geometry_diagnostic_exact": bc_geometry_exact,
        "gates": {
            "B_C_differing_page_sets_equal": bc_page_sets_equal,
            "B_C_geometry_diagnostic_exact": bc_geometry_exact,
            "differing_pages_nonempty": bool(all_differing_page_sets[0]),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full68-manifest",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_host.json",
    )
    parser.add_argument(
        "--rescore",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_candidate_mmr_rescore_01.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_mmr_geometry_delta_diagnostic_01.json",
    )
    args = parser.parse_args()
    payload = run(args.full68_manifest, args.rescore, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "B_b377_differing_pages": payload["labels"]["B_b377"]["differing_pages"],
                "C_latest_differing_pages": payload["labels"]["C_latest"]["differing_pages"],
                "B_C_differing_page_sets_equal": payload["B_C_differing_page_sets_equal"],
                "B_C_geometry_diagnostic_exact": payload["B_C_geometry_diagnostic_exact"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if all(payload["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
