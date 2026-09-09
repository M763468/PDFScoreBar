from tools.issue277.evaluate_composed_mmr_retry_candidate import (
    _unique_aggregate_num,
    evaluate_record,
    primary_anchored_consensus,
)


def _candidate(value, score, bbox=(20.0, 20.0, 40.0, 40.0)):
    return {
        "value": value,
        "score": score,
        "text": str(value),
        "bbox": list(bbox),
    }


def _staff_run(*candidates):
    return {
        "crop_bounds": [90, 90, 210, 210],
        "ranked_numeric_candidates": list(candidates),
    }


def _point(fraction, found_by_variant=None):
    found_by_variant = found_by_variant or {}
    variants = {}
    for name in ("standard", "no_dilate", "heavy_dilate"):
        value = found_by_variant.get(name)
        variants[name] = {
            "aggregate": {
                "found_num": value,
                "score": 80.0 if value is not None else 0.0,
                "staff_index": 0 if value is not None else None,
            },
            "staff_runs": [
                _staff_run(*([] if value is None else [_candidate(value, 50.0)]))
            ],
        }
    return {
        "fraction": fraction,
        "measure_bbox": [100, 100, 200, 200],
        "source_found_num": None,
        "variant_runs": variants,
    }


def _provenance_record(primary=None, shifted=None):
    zero = _point(0.0, primary)
    plus = _point(0.01, {"no_dilate": shifted} if shifted is not None else {})
    return {
        "page_id": "page_001",
        "score": "fixture",
        "page_name": "page_001",
        "key": [0, 0, 0],
        "expected_skip": 5,
        "native_reference": {"primary_staff_bboxes": [[90, 100, 300, 180]]},
        "sweep": [zero, plus],
    }


def _normalized_record(found=None, vote_counts=None):
    return {
        "page_id": "page_001",
        "policy_results": {
            "full_unmasked": {
                "modes": {
                    "heavy_dilate": {
                        "found_num": found,
                        "support": max((vote_counts or {}).values(), default=(1 if found else 0)),
                        "vote_counts": vote_counts or ({} if found is None else {str(found): 1}),
                    }
                }
            }
        },
    }


def test_primary_anchor_requires_unique_support_of_two():
    point = _point(0.0, {"standard": 6, "no_dilate": 6, "heavy_dilate": 7})
    result = primary_anchored_consensus(point, [[90, 100, 300, 180]])
    assert result["selected_num"] == 6
    assert result["support"] == 2
    assert result["vote_counts"] == {"6": 2, "7": 1}


def test_primary_anchor_abstains_on_singleton():
    point = _point(0.0, {"standard": 6})
    result = primary_anchored_consensus(point, [[90, 100, 300, 180]])
    assert result["selected_num"] is None
    assert result["reason"] == "primary_support_below_2"


def test_unique_aggregate_rejects_vote_tie():
    assert _unique_aggregate_num({"found_num": 6, "vote_counts": {"6": 1, "7": 1}}) is None
    assert _unique_aggregate_num({"found_num": 6, "vote_counts": {"6": 2, "7": 1}}) == 6


def test_composed_candidate_stops_at_primary_without_extra_calls():
    result = evaluate_record(
        _provenance_record(primary={"standard": 6, "no_dilate": 6}),
        _normalized_record(found=9),
    )
    assert result["selected_num"] == 6
    assert result["stage"] == "primary_anchored_consensus"
    assert result["additional_rapidocr_calls"] == 0


def test_composed_candidate_uses_one_normalized_retry():
    result = evaluate_record(
        _provenance_record(primary={}),
        _normalized_record(found=6),
    )
    assert result["selected_num"] == 6
    assert result["stage"] == "normalized_unmasked_heavy_dilate"
    assert result["additional_rapidocr_calls"] == 1


def test_composed_candidate_uses_scale_relative_retry_after_normalized_abstain():
    result = evaluate_record(
        _provenance_record(primary={}, shifted=6),
        _normalized_record(found=None),
    )
    assert result["selected_num"] == 6
    assert result["stage"] == "scale_relative_x1_retry"
    assert result["additional_rapidocr_calls"] == 2


def test_composed_candidate_can_abstain_without_emitting_wrong_numeric():
    result = evaluate_record(
        _provenance_record(primary={}, shifted=None),
        _normalized_record(found=None),
    )
    assert result["selected_num"] is None
    assert result["stage"] == "abstain"
    assert result["outcome"] == "abstain"
