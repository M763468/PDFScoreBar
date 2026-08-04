import json
from pathlib import Path

from tools.issue255.inspect_stage_e_historical_upstream import (
    _box_stage_comparison,
    _by_kind,
    _classify,
    _load_boxes,
)


def test_classify_historical_upstream_artifacts() -> None:
    assert _classify(Path("run/baseline/page/page_detections.json")) == "baseline"
    assert _classify(Path("run/sr/page/page_detections.json")) == "sr"
    assert _classify(Path("run/omr_sr/page/predictions.json")) == "omr"
    assert _classify(Path("run/hybrid_predictions.json")) == "hybrid"
    assert _classify(Path("run/page_debug_3_staff.png")) == "staff_mask"
    assert _classify(Path("run/page_debug_7_clefs_keys.png")) == "clef_mask"


def test_classify_fresh_snapshot_artifacts() -> None:
    assert _classify(Path("snapshot/baseline.json")) == "baseline"
    assert _classify(Path("snapshot/sr.json")) == "sr"


def test_load_boxes_supports_prediction_records(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps({"predictions": [{"bbox": [1, 2, 3, 4]}]}))
    assert _load_boxes(path) == [(1, 2, 3, 4)]


def test_by_kind_groups_records() -> None:
    rows = [{"kind": "baseline", "path": "a"}, {"kind": "baseline", "path": "b"}]
    assert _by_kind(rows) == {"baseline": rows}


def test_box_stage_comparison_finds_first_exact_difference(tmp_path: Path) -> None:
    historical_path = tmp_path / "historical.json"
    fresh_path = tmp_path / "fresh.json"
    historical_path.write_text(json.dumps([[1, 2, 3, 4], [5, 6, 7, 8]]))
    fresh_path.write_text(json.dumps([[1, 2, 3, 4], [9, 10, 11, 12]]))
    historical = [
        {
            "kind": "baseline",
            "path": str(historical_path),
            "box_count": 2,
        }
    ]
    fresh = [
        {
            "kind": "baseline",
            "path": str(fresh_path),
            "box_count": 2,
        }
    ]

    result = _box_stage_comparison(historical, fresh, "baseline")

    assert result is not None
    assert result["exact_common_count"] == 1
    assert result["historical_only_count"] == 1
    assert result["fresh_only_count"] == 1
    assert result["exact_match"] is False
