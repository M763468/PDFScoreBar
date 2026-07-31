"""Issue #255 first-loss boundary classification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE_NAMES = ("fresh_baseline", "current_sr", "current_omr")


def classify_first_loss_boundary(
    *,
    source_trace: Mapping[str, Mapping[str, Any]],
    probe_trace: Mapping[str, Any],
    cnn_scored: Mapping[str, Any],
    cnn_accepted: Mapping[str, Any],
    accepted_final: bool,
) -> str:
    """Return the earliest detector layer at which an accepted target is absent."""
    if accepted_final:
        return "already_accepted_final"
    if not any(source_trace[name]["accepted"] for name in SOURCE_NAMES):
        return "absent_from_all_upstream_detectors"
    if not source_trace["hybrid"]["accepted"]:
        return "hybrid_consensus"
    if not probe_trace.get("row_bands"):
        return "row_band_construction"
    for key, boundary in (
        ("raw", "raw_probe_generation"),
        ("size_filtered", "size_filter"),
        ("heuristic_filtered", "candidate_filter"),
        ("trimmed", "trim"),
        ("final", "probe_final_set"),
    ):
        if not probe_trace[key]["accepted"]:
            return boundary
    if not cnn_scored["accepted"]:
        return "cnn_scoring_input"
    if not cnn_accepted["accepted"]:
        return "cnn_filtering"
    return "final_detector_merge"
