from tools.issue255.evaluate_focused_candidate_rescue import (
    _match_box_details,
    _match_boxes,
)


def test_match_boxes_reports_target_recovery_and_new_fp() -> None:
    accepted = [
        (10, 20, 14, 120),
        (30, 20, 34, 120),
    ]
    current = [
        (10, 20, 14, 120),
        (30, 20, 34, 120),
        (80, 20, 84, 120),
    ]

    assert _match_boxes(accepted, current) == {"tp": 2, "fp": 1, "fn": 0}


def test_match_boxes_does_not_match_one_reference_twice() -> None:
    accepted = [(10, 20, 14, 120)]
    current = [
        (10, 20, 14, 120),
        (10, 20, 14, 120),
    ]

    assert _match_boxes(accepted, current) == {"tp": 1, "fp": 1, "fn": 0}


def test_match_box_details_retains_unmatched_geometry() -> None:
    accepted = [(10, 20, 14, 120), (30, 20, 34, 120)]
    current = [(10, 20, 14, 120), (80, 20, 84, 120)]

    details = _match_box_details(accepted, current)

    assert details["tp"] == 1
    assert details["fp"] == 1
    assert details["fn"] == 1
    assert details["false_positive_boxes"] == [[80, 20, 84, 120]]
    assert details["false_negative_boxes"] == [[30, 20, 34, 120]]
