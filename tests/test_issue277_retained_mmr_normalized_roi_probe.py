from tools.issue277.run_retained_mmr_normalized_roi_probe import (
    aggregate_staff_results,
    consensus_across_modes,
    normalized_roi_bounds,
)


def test_normalized_roi_uses_measure_width_and_staff_height():
    roi = normalized_roi_bounds(
        measure_bbox=[100, 300, 500, 450],
        staff_bbox=[80, 300, 900, 400],
        image_width=1000,
        image_height=800,
        left_fraction=0.10,
        right_fraction=0.90,
    )
    assert roi == [140, 250, 460, 400]


def test_normalized_roi_clamps_to_page():
    roi = normalized_roi_bounds(
        measure_bbox=[0, 10, 200, 100],
        staff_bbox=[0, 10, 500, 90],
        image_width=180,
        image_height=120,
        left_fraction=0.0,
        right_fraction=1.0,
    )
    assert roi == [0, 0, 180, 90]


def test_staff_aggregate_uses_majority_then_best_score_for_tie():
    aggregate = aggregate_staff_results(
        [
            {"selected_num": 10, "selected_score": 4.0},
            {"selected_num": 11, "selected_score": 5.0},
            {"selected_num": 10, "selected_score": 3.0},
        ]
    )
    assert aggregate["found_num"] == 10
    assert aggregate["support"] == 2

    tie = aggregate_staff_results(
        [
            {"selected_num": 10, "selected_score": 4.0},
            {"selected_num": 11, "selected_score": 5.0},
        ]
    )
    assert tie["found_num"] == 11
    assert tie["support"] == 1


def test_mode_consensus_prefers_repeated_value():
    result = consensus_across_modes(
        {
            "standard": {"found_num": 3, "best_score": 8.0},
            "no_dilate": {"found_num": 3, "best_score": 7.0},
            "heavy_dilate": {"found_num": 11, "best_score": 20.0},
        }
    )
    assert result["found_num"] == 3
    assert result["support"] == 2
    assert result["vote_counts"] == {"3": 2, "11": 1}
