from tools.issue255.analyze_focused_candidate_multiplicity import (
    Policy,
    _accepted_root_collisions,
    _simulate_policy,
    _stable_match_details,
)


def test_stable_match_locks_exact_baseline_before_approximate_addition() -> None:
    reference = [(10, 20, 14, 120)]
    current = [
        (11, 20, 15, 120),
        (10, 20, 14, 120),
    ]

    details = _stable_match_details(reference, current)

    assert details["tp"] == 1
    assert details["fp"] == 1
    assert details["matches"] == [
        {
            "prediction_index": 1,
            "reference_index": 0,
            "prediction": [10, 20, 14, 120],
            "reference": [10, 20, 14, 120],
            "iou": 1.0,
            "exact": True,
        }
    ]
    assert details["false_positive_boxes"] == [[11, 20, 15, 120]]


def test_policy_preserves_baseline_and_recovers_new_target_without_fp() -> None:
    accepted = [
        (10, 20, 14, 120),
        (100, 20, 104, 120),
    ]
    baseline = [(10, 20, 14, 120)]
    duplicate = (11, 20, 15, 120)
    recovery = (100, 20, 104, 120)
    current = [baseline[0], duplicate, recovery]

    result = _simulate_policy(
        accepted=accepted,
        baseline=baseline,
        current=current,
        scores={duplicate: 0.99, recovery: 0.98},
        targets=[accepted[1]],
        policy=Policy(
            x_tolerance=2,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
        include_details=True,
    )

    assert result["metrics"] == {"tp": 2, "fp": 0, "fn": 0}
    assert result["all_targets_recovered"] is True
    assert result["suppressed_count"] == 1
    assert result["suppressed"][0]["candidate_bbox"] == list(duplicate)
    assert result["accepted_collision_count"] == 0


def test_policy_reports_collision_between_distinct_accepted_barlines() -> None:
    accepted = [
        (10, 20, 14, 120),
        (15, 20, 19, 120),
    ]
    baseline = [accepted[0]]
    current = [accepted[0], accepted[1]]

    result = _simulate_policy(
        accepted=accepted,
        baseline=baseline,
        current=current,
        scores={accepted[1]: 0.99},
        targets=[accepted[1]],
        policy=Policy(
            x_tolerance=5,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
        include_details=True,
    )

    assert result["accepted_collision_count"] == 1
    assert result["all_targets_recovered"] is False
    assert result["accepted_collisions"][0]["candidate_reference_index"] == 1
    assert result["accepted_collisions"][0]["kept_reference_index"] == 0


def test_full_reference_safety_rejects_policy_that_merges_accepted_pair() -> None:
    features = {
        "available": True,
        "page_count": 68,
        "pairs": [
            {
                "path": "accepted/page.json",
                "first_index": 0,
                "first_bbox": [10, 20, 14, 120],
                "second_index": 1,
                "second_bbox": [15, 20, 19, 120],
                "x_distance": 5.0,
                "vertical_overlap_ratio": 1.0,
                "height_ratio": 1.0,
            }
        ],
    }

    unsafe = _accepted_root_collisions(
        features,
        Policy(
            x_tolerance=5,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
    )
    safe = _accepted_root_collisions(
        features,
        Policy(
            x_tolerance=4,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
    )

    assert unsafe["collision_count"] == 1
    assert safe["collision_count"] == 0
