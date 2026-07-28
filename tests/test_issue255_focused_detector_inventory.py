from tools.issue255.trace_focused_detector_boundaries import (
    _first_loss_boundary,
    _missing_accepted_boxes,
    _resolve_targets,
)


def _layer(accepted: bool):
    return {"accepted": accepted}


def _probe(**overrides):
    result = {
        "row_bands": [[10, 100]],
        "raw": _layer(True),
        "size_filtered": _layer(True),
        "heuristic_filtered": _layer(True),
        "trimmed": _layer(True),
        "final": _layer(True),
    }
    result.update(overrides)
    return result


def test_missing_accepted_boxes_uses_iou_contract() -> None:
    accepted = [(10, 20, 14, 120), (30, 20, 34, 120)]
    current = [(10, 20, 14, 120)]

    assert _missing_accepted_boxes(accepted, current, accepted_iou=0.5) == [(30, 20, 34, 120)]


def test_resolve_targets_marks_already_present_metadata() -> None:
    targets = _resolve_targets(
        accepted_boxes=[(10, 20, 14, 120)],
        current_boxes=[(10, 20, 14, 120)],
        metadata=[{"id": "target", "accepted_bbox": [10, 20, 14, 120]}],
        accepted_iou=0.5,
    )

    assert targets[0]["status"] == "already_present_in_current_final"


def test_first_loss_classifies_upstream_source_absence() -> None:
    source = {
        "fresh_baseline": _layer(False),
        "current_sr": _layer(False),
        "current_omr": _layer(False),
        "hybrid": _layer(False),
    }

    assert (
        _first_loss_boundary(
            source_trace=source,
            probe_trace=_probe(),
            cnn_scored=_layer(True),
            cnn_accepted=_layer(True),
            accepted_final=False,
        )
        == "baseline_homr"
    )


def test_first_loss_classifies_candidate_filter() -> None:
    source = {
        "fresh_baseline": _layer(True),
        "current_sr": _layer(False),
        "current_omr": _layer(False),
        "hybrid": _layer(True),
    }

    assert (
        _first_loss_boundary(
            source_trace=source,
            probe_trace=_probe(heuristic_filtered=_layer(False)),
            cnn_scored=_layer(False),
            cnn_accepted=_layer(False),
            accepted_final=False,
        )
        == "candidate_filter"
    )


def test_first_loss_classifies_cnn_filtering() -> None:
    source = {
        "fresh_baseline": _layer(True),
        "current_sr": _layer(True),
        "current_omr": _layer(False),
        "hybrid": _layer(True),
    }

    assert (
        _first_loss_boundary(
            source_trace=source,
            probe_trace=_probe(),
            cnn_scored=_layer(True),
            cnn_accepted=_layer(False),
            accepted_final=False,
        )
        == "cnn_filtering"
    )
