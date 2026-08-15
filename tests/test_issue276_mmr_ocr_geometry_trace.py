from __future__ import annotations

import numpy as np

from src.measure_numbering.mmr import MMROCREngine
from tools.issue276.trace_mmr_ocr_geometry import (
    candidate_trace,
    first_divergence,
    perturbations,
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
    assert len(perturbations(bbox)) == 25


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
