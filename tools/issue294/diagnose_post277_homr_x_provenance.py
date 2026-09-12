#!/usr/bin/env python3
"""Trace focused A/B MMR measure-X deltas back through retained #294 artifacts.

Retained-only: no detector/HOMR/SR/OMR/CNN/OCR/MMR inference is executed. The tool
reconstructs A/B numbering from the completed full68 matrix and records whether the
nearest final barline at each differing measure boundary is inherited exactly from
the baseline HOMR/evaluator output and hybrid consensus, or appears only downstream.
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
from tools.issue294.audit_full68_retained_semantics import _boxes, _normalise_boxes
from tools.issue294.diagnose_post277_mmr_decision_path import _differing_keys, _latest_focused
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import (
    DEFAULT_MANIFEST,
    _build_variant_inputs,
)

VARIANTS = (
    ("A_production", "A_pinned", MeasureNumberingPipeline),
    ("B_b377_mapping_guarded", "B_b377", MappingGuardedConnectorPositivePipeline),
)


def _center_x(box: tuple[int, int, int, int]) -> float:
    return (box[0] + box[2]) / 2.0


def _vertical_overlap(box: tuple[int, int, int, int], y1: int, y2: int) -> int:
    return max(0, min(box[3], y2) - max(box[1], y1))


def _nearest_boundary(
    boxes: list[tuple[int, int, int, int]], target_x: int, y1: int, y2: int
) -> dict[str, Any] | None:
    if not boxes:
        return None
    overlapping = [box for box in boxes if _vertical_overlap(box, y1, y2) > 0]
    candidates = overlapping or boxes
    chosen = min(
        candidates,
        key=lambda box: (
            abs(_center_x(box) - target_x),
            -_vertical_overlap(box, y1, y2),
        ),
    )
    return {
        "box": list(chosen),
        "center_x": _center_x(chosen),
        "target_x": int(target_x),
        "center_dx": float(_center_x(chosen) - target_x),
        "edge_dx": int(min((chosen[0] - target_x, chosen[2] - target_x), key=abs)),
        "vertical_overlap": _vertical_overlap(chosen, y1, y2),
    }


def _measure_bbox(base: Mapping[str, Any], system_idx: int, measure_idx: int) -> list[int]:
    measure = base["pages"][0]["systems"][system_idx]["measures"][measure_idx]
    return [int(value) for value in measure["bbox"]]


def _source_trace(
    *,
    target_x: int,
    y1: int,
    y2: int,
    final_boxes: list[tuple[int, int, int, int]],
    hybrid_boxes: list[tuple[int, int, int, int]],
    baseline_boxes: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    nearest = _nearest_boundary(final_boxes, target_x, y1, y2)
    if nearest is None:
        return {"nearest_final": None}
    final_box = tuple(int(v) for v in nearest["box"])
    return {
        "nearest_final": nearest,
        "final_box_exact_in_hybrid": final_box in set(hybrid_boxes),
        "final_box_exact_in_baseline_detection": final_box in set(baseline_boxes),
        "nearest_hybrid": _nearest_boundary(hybrid_boxes, target_x, y1, y2),
        "nearest_baseline_detection": _nearest_boundary(baseline_boxes, target_x, y1, y2),
    }


def run() -> dict[str, Any]:
    focused_path = _latest_focused()
    focused = _load_json(focused_path)
    differing = _differing_keys(focused)
    manifest = _load_json(DEFAULT_MANIFEST)
    matrix_pages = _load_matrix_pages(manifest)
    specs_all = build_page_specs()
    specs = [spec for spec in specs_all if str(spec.page_id) in differing]

    built: dict[str, tuple[list[dict[str, Any]], list[str]]] = {}
    for output_name, matrix_label, factory in VARIANTS:
        bases, _images, _supports, mapping_modes = _build_variant_inputs(
            specs=specs,
            matrix_pages=matrix_pages,
            label=matrix_label,
            pipeline_factory=factory,
        )
        built[output_name] = (bases, mapping_modes)

    pages: dict[str, Any] = {}
    for index, spec in enumerate(specs):
        page_id = str(spec.page_id)
        key = (str(spec.score), str(spec.page_name))
        matrix_page = matrix_pages[key]
        native = matrix_page["modes"]["candidate_native_geometry"]["variants"]
        variants_out: dict[str, Any] = {}
        for output_name, matrix_label, _factory in VARIANTS:
            bases, mapping_modes = built[output_name]
            base = bases[index]
            retained = native[matrix_label]
            baseline_boxes = _boxes(str(retained["baseline_detection"]))
            hybrid_boxes = _boxes(str(retained["hybrid_path"]))
            final_boxes = _normalise_boxes(retained["final_barlines"])
            events: list[dict[str, Any]] = []
            for system_idx, measure_idx in differing[page_id]:
                bbox = _measure_bbox(base, system_idx, measure_idx)
                x1, y1, x2, y2 = bbox
                events.append(
                    {
                        "system": system_idx,
                        "measure": measure_idx,
                        "measure_bbox": bbox,
                        "left_boundary": _source_trace(
                            target_x=x1,
                            y1=y1,
                            y2=y2,
                            final_boxes=final_boxes,
                            hybrid_boxes=hybrid_boxes,
                            baseline_boxes=baseline_boxes,
                        ),
                        "right_boundary": _source_trace(
                            target_x=x2,
                            y1=y1,
                            y2=y2,
                            final_boxes=final_boxes,
                            hybrid_boxes=hybrid_boxes,
                            baseline_boxes=baseline_boxes,
                        ),
                    }
                )
            variants_out[output_name] = {
                "matrix_label": matrix_label,
                "mapping_mode": mapping_modes[index],
                "baseline_detection": str(retained["baseline_detection"]),
                "hybrid_path": str(retained["hybrid_path"]),
                "events": events,
            }

        comparisons: list[dict[str, Any]] = []
        a_events = variants_out["A_production"]["events"]
        b_events = variants_out["B_b377_mapping_guarded"]["events"]
        for a_event, b_event in zip(a_events, b_events):
            comparisons.append(
                {
                    "system": a_event["system"],
                    "measure": a_event["measure"],
                    "measure_bbox_delta_B_minus_A": [
                        int(b - a)
                        for a, b in zip(a_event["measure_bbox"], b_event["measure_bbox"])
                    ],
                }
            )
        pages[page_id] = {"variants": variants_out, "comparisons": comparisons}

    return {
        "schema_version": "issue294.post277_homr_x_provenance.v1",
        "status": "completed",
        "diagnostic_only": True,
        "focused_artifact": str(focused_path),
        "manifest": str(DEFAULT_MANIFEST),
        "contract": {
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
            "numbering_reconstructed_from_retained_inputs": True,
        },
        "interpretation_boundary": (
            "baseline_detection is the HOMR/evaluator producer output; exact inheritance "
            "to hybrid/final localizes a coordinate to that producer boundary but does not "
            "yet distinguish HOMR model/revision from evaluator/compatibility effects"
        ),
        "pages": pages,
    }


def main() -> int:
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
