from tools.issue277.evaluate_retained_mmr_anchor_consensus import (
    candidate_absolute_center,
    candidate_is_measure_staff_anchored,
    choose_anchored_existing_evidence,
)


def _candidate(value: int, score: float, bbox, confidence: float = 0.9):
    return {
        "value": value,
        "score": score,
        "text": str(value),
        "confidence": confidence,
        "bbox": list(bbox),
    }


def _staff_run(*candidates):
    return {
        "crop_bounds": [100, 200, 600, 500],
        "ranked_numeric_candidates": list(candidates),
    }


def _variant(*runs):
    return {"staff_runs": list(runs)}


def test_candidate_center_maps_out_of_preprocess_border():
    run = _staff_run()
    candidate = _candidate(10, 1.0, [20, 20, 40, 60])
    assert candidate_absolute_center(candidate, run) == (110.0, 220.0)


def test_measure_staff_anchor_rejects_right_annotation_and_below_staff():
    measure = [120, 250, 500, 380]
    staff = [100, 250, 900, 350]
    run = _staff_run()

    centered = _candidate(10, 1.0, [200, 40, 240, 80])
    right_annotation = _candidate(42, 1.0, [430, 40, 470, 80])
    below_staff = _candidate(11, 1.0, [200, 190, 240, 230])

    assert candidate_is_measure_staff_anchored(centered, run, measure, staff)
    assert not candidate_is_measure_staff_anchored(right_annotation, run, measure, staff)
    assert not candidate_is_measure_staff_anchored(below_staff, run, measure, staff)


def test_cross_variant_primary_consensus_beats_single_wrong_staff():
    point = {
        "measure_bbox": [120, 250, 500, 380],
        "variant_runs": {
            "standard": _variant(
                _staff_run(_candidate(11, 10.0, [200, 40, 240, 80])),
                _staff_run(_candidate(10, 11.0, [200, 40, 240, 80])),
            ),
            "no_dilate": _variant(
                _staff_run(_candidate(10, 12.0, [200, 40, 240, 80])),
                _staff_run(_candidate(10, 13.0, [200, 40, 240, 80])),
            ),
            "heavy_dilate": _variant(),
        },
    }
    staff_bboxes = [[100, 250, 900, 350], [100, 250, 900, 350]]

    decision = choose_anchored_existing_evidence(point, staff_bboxes)
    assert decision["selected_num"] == 10
    assert decision["reason"] == "primary_consensus"
    assert decision["primary"]["vote_counts"] == {"10": 3, "11": 1}


def test_fallback_consensus_can_override_conflicting_primary_singleton():
    point = {
        "measure_bbox": [120, 250, 500, 380],
        "variant_runs": {
            "standard": _variant(_staff_run()),
            "no_dilate": _variant(_staff_run()),
            "heavy_dilate": _variant(
                _staff_run(_candidate(3, 15.0, [200, 40, 240, 80]))
            ),
            "unmasked_fallback_standard": _variant(
                _staff_run(_candidate(2, 20.0, [200, 40, 240, 80]))
            ),
            "left_wide_unmasked_fallback_standard": _variant(
                _staff_run(_candidate(2, 18.0, [200, 40, 240, 80]))
            ),
        },
    }
    staff_bboxes = [[100, 250, 900, 350]]

    decision = choose_anchored_existing_evidence(point, staff_bboxes)
    assert decision["selected_num"] == 2
    assert decision["reason"] == "fallback_consensus_over_primary_singleton"


def test_unanchored_primary_annotation_does_not_block_fallback():
    point = {
        "measure_bbox": [120, 250, 500, 380],
        "variant_runs": {
            "standard": _variant(
                _staff_run(_candidate(42, -40.0, [430, 40, 470, 80]))
            ),
            "no_dilate": _variant(),
            "heavy_dilate": _variant(),
            "unmasked_fallback_standard": _variant(
                _staff_run(_candidate(2, 20.0, [200, 40, 240, 80]))
            ),
            "left_wide_unmasked_fallback_standard": _variant(
                _staff_run(_candidate(2, 18.0, [200, 40, 240, 80]))
            ),
        },
    }
    staff_bboxes = [[100, 250, 900, 350]]

    decision = choose_anchored_existing_evidence(point, staff_bboxes)
    assert decision["selected_num"] == 2
    assert decision["reason"] == "fallback_no_anchored_primary"
