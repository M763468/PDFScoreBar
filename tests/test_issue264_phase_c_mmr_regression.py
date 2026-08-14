from tools.issue264.run_phase_c_mmr_regression import (
    parse_eval_image_stem,
    physical_counts,
    score_overrides,
)


def test_parse_eval_image_stem_preserves_score_name_and_page():
    assert parse_eval_image_stem("Shostakovich-Sym5-Va_page_013") == (
        "Shostakovich-Sym5-Va",
        "page_013",
    )
    assert parse_eval_image_stem("Va__Prokofiev_Symphony5_page_023") == (
        "Va__Prokofiev_Symphony5",
        "page_023",
    )


def test_score_overrides_counts_detection_on_zero_expected_page_as_fp():
    detected = {
        "measure_overrides": [
            {"page": 4, "system": 2, "measure": 1, "skip": 3},
        ]
    }

    result = score_overrides({"overrides": []}, detected)

    assert result["counts"] == {
        "expected": 0,
        "detected": 1,
        "matched_tp": 0,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 1,
    }
    assert result["unexpected"] == [
        {
            "key": [4, 2, 1],
            "detected_skip": 3,
            "detected_comment": None,
        }
    ]


def test_score_overrides_separates_match_miss_mismatch_and_unexpected():
    expected = {
        "overrides": [
            {"page": 0, "system": 0, "measure": 0, "skip": 2},
            {"page": 0, "system": 0, "measure": 1, "skip": 3},
            {"page": 0, "system": 0, "measure": 2, "skip": 4},
        ]
    }
    detected = {
        "measure_overrides": [
            {"page": 0, "system": 0, "measure": 0, "skip": 2},
            {"page": 0, "system": 0, "measure": 1, "skip": 7},
            {"page": 0, "system": 0, "measure": 3, "skip": 5},
        ]
    }

    result = score_overrides(expected, detected)

    assert result["counts"] == {
        "expected": 3,
        "detected": 3,
        "matched_tp": 1,
        "missed_fn": 1,
        "skip_mismatch": 1,
        "unexpected_fp": 1,
    }
    assert result["matched"] == [{"key": [0, 0, 0], "skip": 2}]
    assert result["missed"] == [{"key": [0, 0, 2], "expected_skip": 4}]
    assert result["skip_mismatch"][0]["key"] == [0, 0, 1]
    assert result["unexpected"][0]["key"] == [0, 0, 3]


def test_physical_counts_reads_one_page_system_lengths():
    payload = {
        "pages": [
            {
                "systems": [
                    {"measures": [{}, {}, {}]},
                    {"measures": [{}, {}]},
                ]
            }
        ]
    }

    assert physical_counts(payload) == [3, 2]
