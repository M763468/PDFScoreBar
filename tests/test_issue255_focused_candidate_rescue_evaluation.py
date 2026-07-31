from tools.issue255.evaluate_focused_candidate_rescue import _match_boxes


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
