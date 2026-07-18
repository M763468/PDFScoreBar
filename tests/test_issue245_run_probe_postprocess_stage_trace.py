from __future__ import annotations

from tools.issue245.run_probe_postprocess_stage_trace import (
    _classify_target_trace,
    _trace_target,
)


def test_classify_trim_collapsed_to_existing_short_box() -> None:
    trace = {
        "raw_detect": {"accepted": True},
        "present_after_initial_size_filter": True,
        "heuristic_drop_reasons": [],
        "present_after_heuristic_filter": True,
        "trimmed_bbox": [10, 20, 14, 80],
        "trimmed_match": {"accepted": False},
        "trimmed_exact_existing": True,
        "present_after_post_trim_size_filter": True,
        "trimmed_exact_in_final": True,
    }
    assert _classify_target_trace(trace) == "trim_collapsed_to_existing_short_box"


def test_classify_heuristic_drop_precedes_trim() -> None:
    trace = {
        "raw_detect": {"accepted": True},
        "present_after_initial_size_filter": True,
        "heuristic_drop_reasons": ["low_ink_ratio"],
        "present_after_heuristic_filter": False,
        "trimmed_bbox": None,
        "trimmed_match": {"accepted": False},
        "trimmed_exact_existing": False,
        "present_after_post_trim_size_filter": False,
        "trimmed_exact_in_final": False,
    }
    assert _classify_target_trace(trace) == "dropped_by_heuristic_filter"


def test_trace_target_records_trim_geometry_collapse() -> None:
    reference = (100, 200, 104, 300)
    raw = (100, 175, 104, 300)
    trimmed = (100, 225, 104, 300)
    captured = {
        "raw_detect": [raw],
        "initial_size_keep": [raw],
        "heuristic_keep": [raw],
        "heuristic_dropped": [],
        "trim_calls": [{"before": raw, "after": trimmed}],
        "post_trim_size_keep": [trimmed],
    }
    result = _trace_target(
        reference=reference,
        captured=captured,
        existing_boxes=[trimmed],
        final_boxes=[trimmed],
    )
    assert result["raw_detect"]["accepted"] is True
    assert result["trimmed_match"]["accepted"] is False
    assert result["trimmed_exact_existing"] is True
    assert result["classification"] == "trim_collapsed_to_existing_short_box"


def test_trace_target_reports_restored_final_candidate() -> None:
    reference = (100, 200, 104, 300)
    raw = (100, 190, 104, 305)
    trimmed = (100, 200, 104, 300)
    captured = {
        "raw_detect": [raw],
        "initial_size_keep": [raw],
        "heuristic_keep": [raw],
        "heuristic_dropped": [],
        "trim_calls": [{"before": raw, "after": trimmed}],
        "post_trim_size_keep": [trimmed],
    }
    result = _trace_target(
        reference=reference,
        captured=captured,
        existing_boxes=[],
        final_boxes=[trimmed],
    )
    assert result["trimmed_match"]["accepted"] is True
    assert result["trimmed_exact_in_final"] is True
    assert result["classification"] == "restored_in_final_output"
