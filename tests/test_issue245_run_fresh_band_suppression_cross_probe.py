from tools.issue245.run_fresh_band_suppression_cross_probe import (
    _classify_target,
    _record_candidate,
    _target_debug_summary,
)


def _final(accepted: bool = False):
    return {"accepted": accepted, "max_iou": 0.0, "best_bbox": None}


def _debug(statuses=(), raw_iou: float = 0.0):
    return {
        "statuses": list(statuses),
        "records": [],
        "raw_accepted": raw_iou > 0,
        "raw_max_iou": raw_iou,
        "raw_best_bbox": None,
        "raw_best_status": None,
    }


def test_record_candidate_uses_record_band() -> None:
    assert _record_candidate({"col": 10, "band": [20, 40]}) == (8, 20, 12, 40)
    assert _record_candidate({"col": None, "band": [20, 40]}) is None


def test_target_debug_summary_keeps_nearby_target_records() -> None:
    payload = {
        "records": [
            {"status": "existing", "col": 101, "band": [10, 30]},
            {"status": "accepted", "col": 102, "band": [10, 30]},
            {"status": "accepted", "col": 200, "band": [10, 30]},
        ]
    }
    summary = _target_debug_summary(payload, (100, 10, 104, 30), x_tolerance=5)
    assert summary["statuses"] == ["accepted", "existing"]
    assert len(summary["records"]) == 2
    assert summary["raw_accepted"] is True
    assert summary["raw_max_iou"] > 0.5


def test_classify_already_present_control() -> None:
    finals = {
        "row_stats_control": _final(True),
        "pad025_iou050": _final(),
    }
    debugs = {name: _debug() for name in finals}
    assert _classify_target(finals, debugs) == "already_present_in_control"


def test_classify_first_restoring_variant() -> None:
    finals = {
        "row_stats_control": _final(),
        "pad025_iou050": _final(),
        "pad050_iou050": _final(True),
    }
    debugs = {name: _debug() for name in finals}
    assert _classify_target(finals, debugs) == "restored_by_pad050_iou050"


def test_classify_raw_candidate_lost_after_scan() -> None:
    finals = {
        "row_stats_control": _final(),
        "pad025_iou050": _final(),
    }
    debugs = {
        "row_stats_control": _debug(("existing",)),
        "pad025_iou050": _debug(("accepted",), raw_iou=0.8),
    }
    assert _classify_target(finals, debugs) == "raw_candidate_lost_after_probe_scan"


def test_classify_existing_suppression() -> None:
    finals = {
        "row_stats_control": _final(),
        "pad025_iou050": _final(),
    }
    debugs = {name: _debug(("existing",)) for name in finals}
    assert _classify_target(finals, debugs) == "still_existing_suppressed"


def test_classify_pre_suppression_rejection() -> None:
    finals = {
        "row_stats_control": _final(),
        "pad025_iou050": _final(),
    }
    debugs = {name: _debug(("scan_ratio_low",)) for name in finals}
    assert _classify_target(finals, debugs) == "probe_scan_rejected_before_existing_suppression"
