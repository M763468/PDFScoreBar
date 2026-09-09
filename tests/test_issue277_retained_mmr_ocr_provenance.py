from src.measure_numbering.mmr import MMROCREngine
from tools.issue277.diagnose_retained_mmr_ocr_provenance import (
    interesting_sweep_indices,
    rank_numeric_candidates,
    selected_variant_name,
)


def _engine() -> MMROCREngine:
    return MMROCREngine(ocr_engine=object())


def test_rank_numeric_candidates_matches_center_weighted_production_choice():
    engine = _engine()
    ocr_result = [
        [[[82, 38], [118, 38], [118, 70], [82, 70]], "10", 0.90],
        [[[170, 4], [198, 4], [198, 24], [170, 24]], "42", 0.99],
    ]

    ranked = rank_numeric_candidates(engine, ocr_result, img_width=200, img_height=100)
    found_num, found_score, _debug = engine.select_best_candidate(
        list(ocr_result), img_width=200, img_height=100
    )

    assert ranked[0]["value"] == found_num == 10
    assert ranked[0]["score"] == found_score
    assert ranked[0]["text"] == "10"
    assert ranked[0]["source"] == "raw"


def test_selected_variant_name_handles_fallback_and_j2_debug():
    assert (
        selected_variant_name(
            "dx=0.01,dy=0.44,h=0.07,raw,variant=left_wide_unmasked_fallback_standard:0"
        )
        == "left_wide_unmasked_fallback_standard"
    )
    assert (
        selected_variant_name(
            "dx=0.20,dy=0.10,h=0.40,raw,variant=no_dilate:0,j2_consensus=3of5"
        )
        == "no_dilate"
    )
    assert selected_variant_name("") is None


def test_interesting_sweep_indices_keep_zero_edges_and_transitions():
    sweep = [
        {"fraction": -0.04, "skip": 9},
        {"fraction": -0.02, "skip": 10},
        {"fraction": -0.01, "skip": 9},
        {"fraction": 0.0, "skip": 9},
        {"fraction": 0.01, "skip": 9},
        {"fraction": 0.02, "skip": 9},
        {"fraction": 0.04, "skip": 10},
    ]

    assert interesting_sweep_indices(sweep) == [0, 1, 2, 3, 5, 6]
