from tools.issue274.rescore_full68_mmr_reuse_geometry_rebased import classify_changed_event


def _item(skip: int) -> dict[str, int]:
    return {"skip": skip}


def test_changed_event_classification_uses_rebased_gt() -> None:
    expected = _item(4)

    assert classify_changed_event(expected, _item(3), _item(4)) == "improvement"
    assert classify_changed_event(expected, _item(4), _item(3)) == "regression"
    assert classify_changed_event(expected, _item(3), _item(2)) == "neutral"


def test_changed_event_without_rebased_gt_is_not_represented() -> None:
    assert classify_changed_event(None, _item(3), _item(4)) == "not_represented_in_gt"
