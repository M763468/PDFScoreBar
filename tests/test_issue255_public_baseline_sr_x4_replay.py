from __future__ import annotations

from pathlib import Path

from tools.issue255.run_public_baseline_sr_scale_variant import _scaled_config
from tools.issue255.run_public_baseline_sr_x4_replay import (
    _box_comparison,
    _classification,
)


def test_scaled_config_overrides_only_sr_scale() -> None:
    source = {
        "run": {"run_id": "example"},
        "detection": {"sr_scale": 2, "cnn_threshold": 0.1},
    }

    result = _scaled_config(lambda _path: source, Path("config.yaml"), 4)

    assert result["detection"] == {"sr_scale": 4, "cnn_threshold": 0.1}
    assert result["run"] == {"run_id": "example"}
    assert source["detection"]["sr_scale"] == 2


def test_box_comparison_reports_exact_set_difference() -> None:
    result = _box_comparison(
        [(0, 0, 4, 100), (10, 0, 14, 100)],
        [(0, 0, 4, 100), (20, 0, 24, 100)],
    )

    assert result == {
        "actual_count": 2,
        "reference_count": 2,
        "exact_common_count": 1,
        "actual_only_count": 1,
        "reference_only_count": 1,
        "exact_match": False,
    }


def test_classification_prefers_exact_historical_reproduction() -> None:
    assert (
        _classification(
            sr_exact=True,
            hybrid_exact=True,
            image_shape_match=True,
        )
        == "historical_sr_and_hybrid_reproduced"
    )
    assert (
        _classification(
            sr_exact=False,
            hybrid_exact=False,
            image_shape_match=True,
        )
        == "x4_image_geometry_restored_but_detection_or_hybrid_differs"
    )
    assert (
        _classification(
            sr_exact=False,
            hybrid_exact=False,
            image_shape_match=False,
        )
        == "x4_image_geometry_not_restored"
    )
