from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter
from tools.issue245.analyze_hybrid_row_band_source_drift import (
    _classify,
    _row_clusters,
    build_report,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _detections(boxes: list[list[int]]) -> dict[str, object]:
    return {"predictions": [{"orig_bbox": box} for box in boxes]}


def _consensus(
    baseline: list[list[int]],
    sr: list[list[int]],
    omr: list[list[int]],
) -> list[list[int]]:
    return apply_hybrid_consensus_filter(
        baseline_boxes=baseline,
        sr_boxes=sr,
        omr_boxes=omr,
    )


def _fixture(
    tmp_path: Path,
    *,
    historical_sr: list[list[int]],
    historical_omr: list[list[int]],
    current_sr: list[list[int]],
    current_omr: list[list[int]],
) -> tuple[Path, Path, list[dict[str, object]]]:
    root = tmp_path / "repo"
    score = "Score"
    page = "page_001"
    top = [10, 10, 14, 110]
    lower = [20, 10, 24, 110]
    short = [10, 60, 14, 110]
    baseline = [top, lower, short]

    historical_run = root / "historical_run"
    historical_baseline_path = _write_json(
        historical_run / "baseline" / "batch" / page / f"{page}_detections.json",
        _detections(baseline),
    )
    historical_sr_path = _write_json(
        historical_run / "sr" / "batch" / page / f"{page}_detections.json",
        _detections(historical_sr),
    )
    historical_omr_path = _write_json(
        historical_run / "omr_sr" / page / "predictions.json", historical_omr
    )
    historical_hybrid_path = _write_json(
        historical_run / "hybrid_results" / f"{page}_hybrid.json",
        _consensus(baseline, historical_sr, historical_omr),
    )
    historical_inventory = _write_json(
        root / "historical_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "hybrid_predictions": str(historical_hybrid_path.relative_to(root)),
                }
            ]
        },
    )

    fresh_baseline = _write_json(root / "fresh_baseline.json", _detections(baseline))
    current_sr_path = _write_json(root / "current_sr.json", _detections(current_sr))
    current_omr_path = _write_json(root / "current_omr.json", current_omr)
    mixed_hybrid = _write_json(
        root / "mixed_hybrid.json",
        _consensus(baseline, current_sr, current_omr),
    )

    mixed_report = _write_json(
        root / "mixed_report.json",
        {
            "status": "completed",
            "historical_inventory": {"path": str(historical_inventory.relative_to(root))},
            "pages": [
                {
                    "score": score,
                    "page": page,
                    "fresh_baseline": str(fresh_baseline.relative_to(root)),
                    "current_sr": str(current_sr_path.relative_to(root)),
                    "current_omr": str(current_omr_path.relative_to(root)),
                    "historical_hybrid": str(historical_hybrid_path.relative_to(root)),
                    "mixed_hybrid": str(mixed_hybrid.relative_to(root)),
                }
            ],
        },
    )
    assert historical_baseline_path.exists()
    assert historical_sr_path.exists()
    assert historical_omr_path.exists()
    return root, mixed_report, [{"score": score, "page": page, "reference": top}]


def test_row_clusters_use_median_top_and_bottom() -> None:
    rows = _row_clusters([(0, 10, 2, 110), (10, 12, 12, 108), (20, 50, 22, 110)])
    assert rows[0]["top"] == 12
    assert rows[0]["bottom"] == 110
    assert len(rows[0]["members"]) == 3


def test_classify_historical_sr_dependency() -> None:
    variants = {
        "historical_sr_historical_omr": {"reference_band_present": True},
        "historical_sr_current_omr": {"reference_band_present": True},
        "current_sr_historical_omr": {"reference_band_present": False},
        "current_sr_current_omr": {"reference_band_present": False},
    }
    assert _classify(variants) == "historical_sr_dependency"


def test_classify_historical_omr_dependency() -> None:
    variants = {
        "historical_sr_historical_omr": {"reference_band_present": True},
        "historical_sr_current_omr": {"reference_band_present": False},
        "current_sr_historical_omr": {"reference_band_present": True},
        "current_sr_current_omr": {"reference_band_present": False},
    }
    assert _classify(variants) == "historical_omr_dependency"


def test_classify_combined_dependency() -> None:
    variants = {
        "historical_sr_historical_omr": {"reference_band_present": True},
        "historical_sr_current_omr": {"reference_band_present": False},
        "current_sr_historical_omr": {"reference_band_present": False},
        "current_sr_current_omr": {"reference_band_present": False},
    }
    assert _classify(variants) == "combined_historical_sr_omr_dependency"


def test_report_attributes_missing_band_to_historical_sr(tmp_path: Path) -> None:
    full = [[10, 10, 14, 110], [20, 10, 24, 110]]
    root, mixed_report, targets = _fixture(
        tmp_path,
        historical_sr=full,
        historical_omr=[],
        current_sr=[[10, 60, 14, 110]],
        current_omr=[],
    )

    report = build_report(
        main_repo_root=root,
        mixed_report_path=mixed_report,
        targets=targets,
    )

    target = report["targets"][0]
    assert target["classification"] == "historical_sr_dependency"
    assert target["baseline_semantic_comparison"]["semantic_equal"] is True
    assert target["historical_consensus_reproduction"]["semantic_equal"] is True
    assert target["current_consensus_reproduction"]["semantic_equal"] is True
    missing = [
        item
        for item in target["relevant_baseline_candidate_provenance"]
        if item["historical_selected"] and not item["mixed_selected"]
    ]
    assert missing
    assert missing[0]["historical_sr"]["accepted"] is True
    assert missing[0]["current_sr"]["accepted"] is False


def test_report_attributes_missing_band_to_historical_omr(tmp_path: Path) -> None:
    full = [[10, 10, 14, 110], [20, 10, 24, 110]]
    root, mixed_report, targets = _fixture(
        tmp_path,
        historical_sr=[],
        historical_omr=full,
        current_sr=[],
        current_omr=[[10, 60, 14, 110]],
    )

    report = build_report(
        main_repo_root=root,
        mixed_report_path=mixed_report,
        targets=targets,
    )

    assert report["targets"][0]["classification"] == "historical_omr_dependency"
