from __future__ import annotations

import json
from pathlib import Path

from tools.issue255.compare_stage_e_historical_inputs import (
    _artifact,
    _box_comparison,
    _record,
)


def _write_boxes(path: Path, boxes: list[list[int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(boxes), encoding="utf-8")


def test_record_selects_score_and_page() -> None:
    payload = {
        "records": [
            {"score": "A", "page": "page_001"},
            {"score": "B", "page": "page_002"},
        ]
    }

    assert _record(payload, "B", "page_002")["score"] == "B"


def test_artifact_derives_clef_mask_from_staff_debug(tmp_path: Path) -> None:
    staff = tmp_path / "page_004_proxy_debug_3_staff.png"
    clef = tmp_path / "page_004_proxy_debug_7_clefs_keys.png"
    staff.touch()
    clef.touch()
    record = {
        "score": "A",
        "page": "page_004",
        "staff_mask": str(staff),
    }

    assert _artifact(record, "clef_mask") == clef


def test_box_comparison_reports_exact_delta(tmp_path: Path) -> None:
    historical = tmp_path / "historical.json"
    current = tmp_path / "current.json"
    _write_boxes(historical, [[1, 2, 3, 4], [10, 20, 30, 40]])
    _write_boxes(current, [[1, 2, 3, 4], [11, 20, 31, 40]])

    result = _box_comparison(historical, current)

    assert result["exact_match"] is False
    assert result["missing_from_current"] == [[10, 20, 30, 40]]
    assert result["extra_in_current"] == [[11, 20, 31, 40]]
