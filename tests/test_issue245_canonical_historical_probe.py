from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.issue245.run_canonical_historical_probe import (
    build_comparison_report,
    current_detection_paths,
    discover_historical_detection,
)


def write_detection(path: Path, boxes: list[list[int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "predictions": [
                    {
                        "orig_bbox": box,
                        "pred_bbox": box,
                        "system_index": index,
                        "staff_index": -1,
                    }
                    for index, box in enumerate(boxes)
                ]
            }
        ),
        encoding="utf-8",
    )


def test_discover_historical_detection_prefers_expected_layout(tmp_path: Path) -> None:
    expected = (
        tmp_path
        / "baseline"
        / "page_001"
        / "page_001"
        / "page_001_detections.json"
    )
    write_detection(expected, [[1, 2, 3, 4]])

    assert discover_historical_detection(tmp_path) == expected


def test_discover_historical_detection_rejects_ambiguous_fallback(tmp_path: Path) -> None:
    write_detection(tmp_path / "baseline/a/a_detections.json", [[1, 2, 3, 4]])
    write_detection(tmp_path / "baseline/b/b_detections.json", [[5, 6, 7, 8]])

    with pytest.raises(RuntimeError, match="ambiguous"):
        discover_historical_detection(tmp_path)


def test_current_detection_paths_match_route_layouts(tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    paths = current_detection_paths(tmp_path / "out", "run", image)

    assert paths["production_in_process"] == (
        tmp_path
        / "out/in_process/run/baseline/batch/page_001/page_001_detections.json"
    )
    assert paths["evaluator_default_thin"] == (
        tmp_path / "out/evaluator/run/page_001/page_001_detections.json"
    )
    assert paths["in_process_no_thin"] == (
        tmp_path / "out/no_thin/run/baseline/batch/page_001/page_001_detections.json"
    )


def test_build_comparison_report_compares_each_current_route(tmp_path: Path) -> None:
    historical = tmp_path / "historical.json"
    write_detection(historical, [[10, 0, 12, 100], [30, 0, 32, 100]])

    current_paths = {
        "production_in_process": tmp_path / "production.json",
        "evaluator_default_thin": tmp_path / "evaluator.json",
        "in_process_no_thin": tmp_path / "no_thin.json",
    }
    write_detection(current_paths["production_in_process"], [[11, 0, 13, 100]])
    write_detection(
        current_paths["evaluator_default_thin"],
        [[11, 0, 13, 100], [31, 0, 33, 100]],
    )
    write_detection(current_paths["in_process_no_thin"], [[31, 0, 33, 100]])

    report = build_comparison_report(historical, current_paths)

    assert report["historical_count"] == 2
    assert report["comparisons"]["production_in_process"]["matched_count"] == 1
    assert report["comparisons"]["evaluator_default_thin"]["matched_count"] == 2
    assert report["comparisons"]["in_process_no_thin"]["matched_count"] == 1
