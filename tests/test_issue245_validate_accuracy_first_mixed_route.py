import json
from pathlib import Path

import pytest

from tools.issue245 import validate_accuracy_first_mixed_route as validator


def _write_boxes(path: Path, boxes: list[list[int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(boxes), encoding="utf-8")


def test_load_hybrid_records_reads_top_level_box_array(tmp_path: Path) -> None:
    path = tmp_path / "hybrid.json"
    _write_boxes(path, [[10, 20, 12, 100], [30, 40, 32, 120]])

    records = validator.load_hybrid_records(path)

    assert [record["box"] for record in records] == [
        [10.0, 20.0, 12.0, 100.0],
        [30.0, 40.0, 32.0, 120.0],
    ]


def test_validate_report_rejects_zero_historical_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(validator, "EXPECTED_PAGES", 1)
    monkeypatch.setattr(validator, "EXPECTED_HISTORICAL_HYBRID_COUNT", 1)
    historical = tmp_path / "historical.json"
    mixed = tmp_path / "mixed.json"
    _write_boxes(historical, [])
    _write_boxes(mixed, [])
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "score": "Va_Prokofiev_Symphony1",
                        "page": "page_001",
                        "historical_hybrid": str(historical),
                        "mixed_hybrid": str(mixed),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Historical hybrid count"):
        validator.validate_report(tmp_path, report)


def test_validate_report_recomputes_nonzero_comparison(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(validator, "EXPECTED_PAGES", 1)
    monkeypatch.setattr(validator, "EXPECTED_HISTORICAL_HYBRID_COUNT", 2)
    historical = tmp_path / "historical.json"
    mixed = tmp_path / "mixed.json"
    _write_boxes(historical, [[10, 20, 12, 100], [30, 40, 32, 120]])
    _write_boxes(mixed, [[11, 20, 13, 100], [50, 40, 52, 120]])
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "score": "Va_Prokofiev_Symphony1",
                        "page": "page_001",
                        "historical_hybrid": str(historical),
                        "mixed_hybrid": str(mixed),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validator.validate_report(tmp_path, report)
    aggregate = result["aggregate_comparison_to_historical_hybrid"]

    assert aggregate == {
        "pages": 1,
        "pages_semantic_equal": 0,
        "pages_different": 1,
        "historical_count": 2,
        "mixed_count": 2,
        "matched_count": 1,
        "historical_only_count": 1,
        "mixed_only_count": 1,
        "differing_pages": ["Va_Prokofiev_Symphony1/page_001"],
    }
