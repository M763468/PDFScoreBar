#!/usr/bin/env python3
"""Trace focused Issue #294 A/B measure edges to real/ghost barlines and staff geometry.

Retained-only diagnostic. It reconstructs current Phase-A numbering from the completed
Issue #294 full68 matrix and reports, for the focused A/B-differing MMR keys, whether
measure x1/x2 come from detected barline edges or an implicit system-start ghost.
No detector/HOMR/SR/OMR/CNN/OCR/MMR inference is run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294._mapping_guarded_candidate_mmr_rescore import _run_numbering_score
from tools.issue294.audit_full68_retained_semantics import _boxes, _normalise_boxes
from tools.issue294.diagnose_post277_mmr_decision_path import _differing_keys, _latest_focused
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import DEFAULT_MANIFEST

VARIANTS = (
    ("A_production", "A_pinned", MeasureNumberingPipeline),
    ("B_b377_mapping_guarded", "B_b377", MappingGuardedConnectorPositivePipeline),
)


def _bbox(box: Any) -> list[int]:
    return [int(box.x1), int(box.y1), int(box.x2), int(box.y2)]


def _bar_payload(bar: Any) -> dict[str, Any]:
    bbox = _bbox(bar.bbox)
    return {
        "bbox": bbox,
        "center_x": (bbox[0] + bbox[2]) / 2.0,
        "width": bbox[2] - bbox[0],
        "is_ghost": bool(bar.is_ghost),
    }


def _edge_payload(measure: Any, side: str) -> dict[str, Any]:
    bar = measure.start_bar if side == "left" else measure.end_bar
    if bar is None:
        return {"source": "none", "bar": None}
    return {
        "source": "implicit_staff_sys_x1" if bool(bar.is_ghost) else "detected_barline",
        "bar": _bar_payload(bar),
    }


def _exact_membership(bar: Any, *, baseline: list[tuple[int, int, int, int]], hybrid: list[tuple[int, int, int, int]], final: list[tuple[int, int, int, int]]) -> dict[str, Any]:
    if bar is None or bool(bar.is_ghost):
        return {"baseline": False, "hybrid": False, "final": False}
    raw = tuple(_bbox(bar.bbox))
    return {
        "baseline": raw in set(baseline),
        "hybrid": raw in set(hybrid),
        "final": raw in set(final),
    }


def run() -> dict[str, Any]:
    focused_path = _latest_focused()
    focused = _load_json(focused_path)
    differing = _differing_keys(focused)
    manifest = _load_json(DEFAULT_MANIFEST)
    matrix_pages = _load_matrix_pages(manifest)
    specs = [spec for spec in build_page_specs() if str(spec.page_id) in differing]

    pages: dict[str, Any] = {}
    for spec in specs:
        page_id = str(spec.page_id)
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        native = matrix_page["modes"]["candidate_native_geometry"]["variants"]
        variants: dict[str, Any] = {}

        for output_name, matrix_label, factory in VARIANTS:
            pipeline = factory()
            score = _run_numbering_score(
                matrix_page,
                mode="candidate_native_geometry",
                label=matrix_label,
                page_number=int(spec.global_index) + 1,
                pipeline=pipeline,
            )
            retained = native[matrix_label]
            baseline = _boxes(str(retained["baseline_detection"]))
            hybrid = _boxes(str(retained["hybrid_path"]))
            final = _normalise_boxes(retained["final_barlines"])

            events: list[dict[str, Any]] = []
            for system_idx, measure_idx in differing[page_id]:
                system = score.pages[0].systems[system_idx]
                measure = system.measures[measure_idx]
                staff_bboxes = [_bbox(staff.bbox) for staff in system.staves]
                left = _edge_payload(measure, "left")
                right = _edge_payload(measure, "right")
                left["exact_membership"] = _exact_membership(
                    measure.start_bar, baseline=baseline, hybrid=hybrid, final=final
                )
                right["exact_membership"] = _exact_membership(
                    measure.end_bar, baseline=baseline, hybrid=hybrid, final=final
                )
                events.append(
                    {
                        "system": system_idx,
                        "measure": measure_idx,
                        "measure_bbox": _bbox(measure.bbox),
                        "system_staff_x1": [bbox[0] for bbox in staff_bboxes],
                        "system_staff_x2": [bbox[2] for bbox in staff_bboxes],
                        "system_x1": min(bbox[0] for bbox in staff_bboxes),
                        "system_x2": max(bbox[2] for bbox in staff_bboxes),
                        "left": left,
                        "right": right,
                    }
                )
            variants[output_name] = {
                "mapping_mode": str(getattr(pipeline, "last_evidence_geometry_mode", "production")),
                "events": events,
            }

        comparisons: list[dict[str, Any]] = []
        a_events = variants["A_production"]["events"]
        b_events = variants["B_b377_mapping_guarded"]["events"]
        for a, b in zip(a_events, b_events):
            item = {
                "system": a["system"],
                "measure": a["measure"],
                "measure_bbox_delta_B_minus_A": [bb - aa for aa, bb in zip(a["measure_bbox"], b["measure_bbox"])],
                "system_x1_delta_B_minus_A": b["system_x1"] - a["system_x1"],
                "left_source_A": a["left"]["source"],
                "left_source_B": b["left"]["source"],
                "right_source_A": a["right"]["source"],
                "right_source_B": b["right"]["source"],
            }
            for side in ("left", "right"):
                abar = a[side].get("bar")
                bbar = b[side].get("bar")
                if abar and bbar:
                    item[f"{side}_bar_center_delta_B_minus_A"] = bbar["center_x"] - abar["center_x"]
                    item[f"{side}_bar_width_delta_B_minus_A"] = bbar["width"] - abar["width"]
                else:
                    item[f"{side}_bar_center_delta_B_minus_A"] = None
                    item[f"{side}_bar_width_delta_B_minus_A"] = None
            comparisons.append(item)
        pages[page_id] = {"variants": variants, "comparisons": comparisons}

    return {
        "schema_version": "issue294.post277_measure_boundary_sources.v1",
        "status": "completed",
        "diagnostic_only": True,
        "focused_artifact": str(focused_path),
        "manifest": str(DEFAULT_MANIFEST),
        "contract": {
            "inference_reexecuted": False,
            "numbering_reconstructed_from_retained_inputs": True,
        },
        "pages": pages,
    }


def main() -> int:
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
