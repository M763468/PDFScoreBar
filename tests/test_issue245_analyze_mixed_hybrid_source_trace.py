from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.issue245.analyze_mixed_hybrid_source_trace import build_report, main


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _detections(boxes: list[list[int]]) -> dict[str, object]:
    return {"predictions": [{"orig_bbox": box} for box in boxes]}


def _build_fixture(
    tmp_path: Path,
    *,
    baseline: list[list[int]],
    sr: list[list[int]],
    omr: list[list[int]],
    saved_mixed: list[list[int]],
    historical_baseline: list[list[int]],
) -> tuple[Path, Path, list[dict[str, object]]]:
    root = tmp_path / "repo"
    mixed_root = root / "logs" / "mixed"
    score = "Score"
    page = "page_001"
    fresh_path = _write_json(root / "fresh.json", _detections(baseline))
    sr_path = _write_json(root / "sr.json", _detections(sr))
    omr_path = _write_json(root / "omr.json", omr)
    mixed_path = _write_json(root / "mixed.json", saved_mixed)
    run_dir = root / "logs" / "historical_run"
    _write_json(
        run_dir / "baseline" / page / page / f"{page}_detections.json",
        _detections(historical_baseline),
    )
    historical_hybrid = _write_json(root / "historical_hybrid.json", [])
    historical_inventory = _write_json(
        root / "historical_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "run_dir": str(run_dir.relative_to(root)),
                    "hybrid_predictions": str(historical_hybrid.relative_to(root)),
                }
            ]
        },
    )
    _write_json(
        mixed_root / "accuracy_first_mixed_route_report.json",
        {
            "historical_inventory": {"path": str(historical_inventory.relative_to(root))},
            "pages": [
                {
                    "score": score,
                    "page": page,
                    "fresh_baseline": str(fresh_path.relative_to(root)),
                    "current_sr": str(sr_path.relative_to(root)),
                    "current_omr": str(omr_path.relative_to(root)),
                    "mixed_hybrid": str(mixed_path.relative_to(root)),
                }
            ],
        },
    )
    targets = [
        {
            "score": score,
            "page": page,
            "reference": (10, 10, 14, 110),
            "short": (10, 60, 14, 110),
        }
    ]
    return root, mixed_root, targets


def test_baseline_exact_candidate_is_accepted_with_sr_support(tmp_path: Path) -> None:
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[[10, 10, 14, 110]],
        sr=[[10, 10, 14, 110]],
        omr=[],
        saved_mixed=[[10, 10, 14, 110]],
        historical_baseline=[[10, 10, 14, 110]],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    target = report["targets"][0]
    assert target["fresh_baseline_comparison"]["accepted_by_regenerated_consensus"] is True
    assert target["current_sr_support"]["max_iou"] == 1.0
    assert report["page_reproduction"][0]["semantic_equal"] is True


def test_baseline_exact_candidate_is_accepted_with_omr_support(tmp_path: Path) -> None:
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[[10, 10, 14, 110]],
        sr=[],
        omr=[[10, 10, 14, 110]],
        saved_mixed=[[10, 10, 14, 110]],
        historical_baseline=[[10, 10, 14, 110]],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    assert report["targets"][0]["current_omr_support"]["accepted_by_source"] is True


def test_baseline_exact_candidate_without_support_is_classified_as_support_loss(
    tmp_path: Path,
) -> None:
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[[10, 10, 14, 110]],
        sr=[],
        omr=[],
        saved_mixed=[],
        historical_baseline=[[10, 10, 14, 110]],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    assert report["targets"][0]["cause_classification"] == "current_support_loss"


def test_short_mixed_bbox_is_identified_as_fresh_baseline_candidate(tmp_path: Path) -> None:
    short = [10, 60, 14, 110]
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[short],
        sr=[short],
        omr=[],
        saved_mixed=[short],
        historical_baseline=[short],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    target = report["targets"][0]
    assert target["mixed_short_candidate"]["fresh_baseline_exact"] is True
    assert target["mixed_short_candidate"]["accepted_by_regenerated_consensus"] is True
    assert target["cause_classification"] == "fresh_baseline_geometry_loss"


def test_missing_fresh_reference_is_classified_as_geometry_loss(tmp_path: Path) -> None:
    short = [10, 60, 14, 110]
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[short],
        sr=[short],
        omr=[],
        saved_mixed=[short],
        historical_baseline=[[10, 10, 14, 110]],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    assert report["targets"][0]["cause_classification"] == "fresh_baseline_geometry_loss"


def test_report_records_paths_and_mismatch_is_not_semantically_equal(tmp_path: Path) -> None:
    root, mixed_root, targets = _build_fixture(
        tmp_path,
        baseline=[[10, 10, 14, 110]],
        sr=[[10, 10, 14, 110]],
        omr=[],
        saved_mixed=[],
        historical_baseline=[[10, 10, 14, 110]],
    )

    report = build_report(main_repo_root=root, mixed_route_root=mixed_root, targets=targets)

    target = report["targets"][0]
    assert target["current_sr_support"]["path"].endswith("sr.json")
    assert target["current_sr_support"]["max_iou"] == 1.0
    assert report["page_reproduction"][0]["semantic_equal"] is False


def test_main_returns_nonzero_when_saved_mixed_differs(tmp_path: Path, monkeypatch: object) -> None:
    root, mixed_root, _ = _build_fixture(
        tmp_path,
        baseline=[[10, 10, 14, 110]],
        sr=[[10, 10, 14, 110]],
        omr=[],
        saved_mixed=[],
        historical_baseline=[[10, 10, 14, 110]],
    )
    output = tmp_path / "trace.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trace",
            "--main-repo-root",
            str(root),
            "--mixed-route-root",
            str(mixed_root),
            "--target",
            "Score|page_001|10,10,14,110|10,60,14,110",
            "--output",
            str(output),
        ],
    )

    assert main() == 2
    assert output.exists()
