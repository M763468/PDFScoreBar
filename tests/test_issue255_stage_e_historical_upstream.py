import json
from pathlib import Path

from tools.issue255.inspect_stage_e_historical_upstream import _by_kind, _classify, _load_boxes


def test_classify_historical_upstream_artifacts() -> None:
    assert _classify(Path("run/baseline/page/page_detections.json")) == "baseline"
    assert _classify(Path("run/sr/page/page_detections.json")) == "sr"
    assert _classify(Path("run/omr_sr/page/predictions.json")) == "omr"
    assert _classify(Path("run/hybrid_predictions.json")) == "hybrid"
    assert _classify(Path("run/page_debug_3_staff.png")) == "staff_mask"
    assert _classify(Path("run/page_debug_7_clefs_keys.png")) == "clef_mask"


def test_load_boxes_supports_prediction_records(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps({"predictions": [{"bbox": [1, 2, 3, 4]}]}))
    assert _load_boxes(path) == [(1, 2, 3, 4)]


def test_by_kind_groups_records() -> None:
    rows = [{"kind": "baseline", "path": "a"}, {"kind": "baseline", "path": "b"}]
    assert _by_kind(rows) == {"baseline": rows}
