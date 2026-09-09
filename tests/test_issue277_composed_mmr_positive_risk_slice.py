from tools.issue277.run_composed_mmr_positive_risk_slice import (
    choose_anchored_consensus,
    scale_relative_x1_bbox,
    unique_vote,
)


def test_unique_vote_rejects_ties_and_ones():
    assert unique_vote([1, 1, None, 2, 3]) is None
    assert unique_vote([1, 2, 2, 3]) == 2
    assert unique_vote([None, 1]) is None


def test_scale_relative_x1_bbox_uses_measure_width():
    assert scale_relative_x1_bbox([398, 1350, 836, 1506], 0.01) == [402, 1350, 836, 1506]
    assert scale_relative_x1_bbox([100, 10, 500, 20], 0.02) == [108, 10, 500, 20]


def test_primary_consensus_requires_unique_support_of_two():
    evidence = [{"value": 10}, {"value": 10}, {"value": 2}]
    assert choose_anchored_consensus(evidence) == (10, 2, {"2": 1, "10": 2})

    tie = [{"value": 10}, {"value": 10}, {"value": 2}, {"value": 2}]
    assert choose_anchored_consensus(tie) == (None, 2, {"2": 2, "10": 2})

    low_support = [{"value": 10}]
    assert choose_anchored_consensus(low_support) == (None, 1, {"10": 1})
