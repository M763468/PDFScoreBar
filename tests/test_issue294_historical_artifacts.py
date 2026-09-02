from pathlib import Path

from tools.issue294.compare_same_original_ab_historical import _optional_mask_comparison
from tools.issue294.run_same_original_ab_historical import historical_artifact_paths
from tools.issue294.run_same_original_ab_host_historical import _REWRITES


def test_issue294_historical_pinned_artifacts_use_actual_evaluator_outputs(tmp_path: Path) -> None:
    artifacts = historical_artifact_paths(tmp_path, "page_013")

    assert set(artifacts) == {"detections", "staff_overlay", "notehead_overlay"}
    assert artifacts["detections"].endswith("batch/page_013/page_013_detections.json")
    assert artifacts["staff_overlay"].endswith(
        "batch/page_013/page_013_debug_staff_resized_overlay.png"
    )
    assert artifacts["notehead_overlay"].endswith(
        "batch/page_013/page_013_debug_notehead_resized_overlay.png"
    )


def test_issue294_missing_historical_raw_mask_is_reported_not_fabricated() -> None:
    result = _optional_mask_comparison(
        {"staff_overlay": "/tmp/A_staff_overlay.png"},
        {"staff_mask": "/tmp/B_staff_mask.png"},
        "staff_mask",
        "staff_overlay",
    )

    assert result["available"] is False
    assert result["reason"] == (
        "historical_pinned_evaluator_does_not_materialize_raw_mask_artifact"
    )
    assert result["A_diagnostic_overlay"] == "/tmp/A_staff_overlay.png"
    assert result["B_raw_mask"] == "/tmp/B_staff_mask.png"


def test_issue294_host_adapter_routes_only_ab_runner_and_comparator() -> None:
    assert _REWRITES == {
        "tools/issue294/run_same_original_ab.py": (
            "tools/issue294/run_same_original_ab_historical.py"
        ),
        "tools/issue294/compare_same_original_ab.py": (
            "tools/issue294/compare_same_original_ab_historical.py"
        ),
    }
