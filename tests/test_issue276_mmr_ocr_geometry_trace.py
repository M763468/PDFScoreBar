from __future__ import annotations

import numpy as np

from src.measure_numbering.mmr import MMROCREngine
from tools.issue276.trace_mmr_ocr_geometry import (
    candidate_image_geometry,
    candidate_trace,
    final_selected_candidate,
    first_divergence,
    perturbations,
    staff_perturbations,
    trace_mask_hbar_candidates,
)


def _item(x1, y1, x2, y2, text, confidence):
    return [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, confidence]


def test_candidate_trace_matches_production_and_preserves_confidence_and_source():
    engine = MMROCREngine(ocr_engine=object())
    result = [_item(40, 20, 55, 70, "1", 0.91), _item(57, 20, 73, 70, "2", 0.82)]
    trace = candidate_trace(engine, result, 120, 100)
    assert (
        trace["production_selection"]["number"] == engine.select_best_candidate(result, 120, 100)[0]
    )
    assert {item["source"] for item in trace["numeric_candidates"]} == {"raw", "merged"}
    assert {item["rapidocr_confidence"] for item in trace["raw_detections"]} == {0.91, 0.82}


def test_trace_mask_matches_production_pixel_for_pixel():
    engine = MMROCREngine(ocr_engine=object())
    image = np.full((100, 120, 3), 255, dtype=np.uint8)
    image[45:52, 10:90] = 0
    masked, records = trace_mask_hbar_candidates(engine, image, 20, 60)
    assert np.array_equal(masked, engine.mask_hbar_candidates(image, 20, 60))
    assert any(item["masked"] for item in records)


def test_perturbations_are_deterministic_and_do_not_mutate_input():
    bbox = [10, 20, 30, 40]
    assert perturbations(bbox) == perturbations(bbox)
    assert bbox == [10, 20, 30, 40]
    assert len(perturbations(bbox)) == 13


def test_staff_perturbations_are_deterministic_non_mutating_and_move_crop():
    system = {"staves": [{"bbox": [0, 20, 100, 80]}], "measures": []}
    first = staff_perturbations(system, 0)
    assert first == staff_perturbations(system, 0)
    assert system["staves"][0]["bbox"] == [0, 20, 100, 80]
    assert first[1]["system"]["staves"][0]["bbox"][1] != 20


def test_processed_candidate_maps_through_border_to_image_coordinates():
    candidate = {"bbox": [[20, 20], [40, 20], [40, 50], [20, 50]]}
    mapped = candidate_image_geometry(candidate, [100, 200, 300, 400], 0)
    assert mapped["candidate_image_bbox"] == [100, 200, 120, 230]
    assert mapped["candidate_image_center"] == [110, 215]


def test_first_divergence_uses_pipeline_order():
    left = {
        "stave_crop_pixels": ["a"],
        "mask_rectangles": [],
        "masked_pixels": ["a"],
        "processed_pixels": ["a"],
        "rapidocr_raw": [],
        "numeric_candidates": [],
        "candidate_ranking": [],
        "selected_number": 2,
        "final_validity": True,
    }
    right = dict(left)
    right["processed_pixels"] = ["b"]
    right["selected_number"] = 5
    assert first_divergence(left, right) == "processed_pixels"


def test_final_selected_candidate_uses_final_variant_not_first_call():
    candidate_42 = {"numeric_value": 42, "spatial_score": 8.0, "selected": True}
    candidate_12 = {"numeric_value": 12, "spatial_score": 4.0, "selected": True}
    trace = {
        "final": {"found_num": 12, "score": 4.0, "selected_variant": "heavy_dilate:0"},
        "variants": [
            {
                "variant": "standard:0",
                "aggregation": {"stave_index": 0},
                "staves": [{"stave_index": 0, "numeric_candidates": [candidate_42]}],
            },
            {
                "variant": "heavy_dilate:0",
                "aggregation": {"stave_index": 0},
                "staves": [{"stave_index": 0, "numeric_candidates": [candidate_12]}],
            },
        ],
    }
    assert final_selected_candidate(trace) == candidate_12
