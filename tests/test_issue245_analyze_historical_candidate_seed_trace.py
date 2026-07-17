from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.issue245.analyze_historical_candidate_seed_trace import (
    build_report,
    resolve_historical_seed_path,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _detections(boxes: list[list[int]]) -> dict[str, object]:
    return {"predictions": [{"orig_bbox": box} for box in boxes]}


def _fixture(
    tmp_path: Path, *, seed_boxes: list[list[int]]
) -> tuple[Path, Path, Path, Path, Path, list[dict[str, object]]]:
    root = tmp_path / "repo"
    score = "Score"
    page = "page_001"
    full_span = [10, 10, 14, 110]
    short = [10, 50, 14, 110]
    historical_run = root / "historical_run"
    _write_json(
        historical_run / "baseline" / "one" / f"{page}_detections.json", _detections([short])
    )
    historical_hybrid = _write_json(root / "historical_hybrid.json", [short])
    inventory = _write_json(
        root / "historical_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "run_dir": str(historical_run.relative_to(root)),
                    "hybrid_predictions": str(historical_hybrid.relative_to(root)),
                }
            ]
        },
    )
    mixed_root = root / "mixed"
    mixed = _write_json(root / "mixed.json", [short])
    _write_json(
        mixed_root / "accuracy_first_mixed_route_report.json",
        {
            "historical_inventory": {"path": str(inventory.relative_to(root))},
            "pages": [{"score": score, "page": page, "mixed_hybrid": str(mixed.relative_to(root))}],
        },
    )
    historical_root = root / "historical_final"
    _write_json(
        historical_root / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json",
        _detections([full_span, short]),
    )
    _write_json(
        historical_root / f"eval2_{score}_{page}" / "pipeline2_no_peak_scored.json",
        _detections([full_span, short]),
    )
    stage_e_root = root / "stage_e"
    _write_json(
        stage_e_root
        / "dense_candidate_reconstruction"
        / "probe_candidates_from_inventory"
        / score
        / page
        / "pipeline2_no_peak_candidates.json",
        _detections([short]),
    )
    _write_json(
        stage_e_root
        / "dense_candidate_reconstruction"
        / "probe_candidates_filtered"
        / score
        / page
        / "pipeline2_no_peak_candidates.json",
        _detections([short]),
    )
    _write_json(
        stage_e_root
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_candidates.json",
        _detections([short]),
    )
    _write_json(
        stage_e_root
        / "intermediate"
        / "probe_scan"
        / f"eval2_images_{score}_{page}"
        / "pipeline2_no_peak_candidates.json",
        _detections([short]),
    )
    v12_root = root / "v12"
    _write_json(
        v12_root / score / page / "pipeline2_no_peak_candidates.json", _detections(seed_boxes)
    )
    targets = [{"score": score, "page": page, "full_span": full_span, "short": short}]
    return root, mixed_root, stage_e_root, historical_root, v12_root, targets


def test_historical_runner_prefers_score_page_candidate_file(tmp_path: Path) -> None:
    _, _, _, _, v12_root, _ = _fixture(tmp_path, seed_boxes=[[10, 10, 14, 110]])
    scored = v12_root / "Score" / "page_001" / "pipeline2_no_peak_scored.json"
    _write_json(scored, _detections([[10, 50, 14, 110]]))

    assert resolve_historical_seed_path(v12_root, "Score", "page_001").name == (
        "pipeline2_no_peak_candidates.json"
    )


def test_historical_runner_falls_back_to_scored_file(tmp_path: Path) -> None:
    _, _, _, _, v12_root, _ = _fixture(tmp_path, seed_boxes=[])
    (v12_root / "Score" / "page_001" / "pipeline2_no_peak_candidates.json").unlink()
    expected = _write_json(
        v12_root / "Score" / "page_001" / "pipeline2_no_peak_scored.json",
        _detections([[10, 10, 14, 110]]),
    )

    assert resolve_historical_seed_path(v12_root, "Score", "page_001") == expected


def test_recursive_seed_discovery_rejects_ambiguous_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "v12"
    _write_json(root / "one" / "Score" / "page_001" / "pipeline2_no_peak_candidates.json", [])
    _write_json(root / "two" / "Score" / "page_001" / "pipeline2_no_peak_scored.json", [])

    with pytest.raises(RuntimeError, match="Ambiguous historical v12 seed"):
        resolve_historical_seed_path(root, "Score", "page_001")


def test_full_span_present_in_v12_seed_is_classified(tmp_path: Path) -> None:
    root, mixed_root, stage_e_root, historical_root, v12_root, targets = _fixture(
        tmp_path, seed_boxes=[[10, 10, 14, 110], [10, 50, 14, 110]]
    )

    report = build_report(
        main_repo_root=root,
        mixed_route_root=mixed_root,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        v12_root=v12_root,
        targets=targets,
    )

    assert report["targets"][0]["classification"] == "full_span_present_in_v12_seed"


def test_full_span_only_in_historical_final_is_classified_as_generated_after_seed(
    tmp_path: Path,
) -> None:
    root, mixed_root, stage_e_root, historical_root, v12_root, targets = _fixture(
        tmp_path, seed_boxes=[[10, 50, 14, 110]]
    )

    report = build_report(
        main_repo_root=root,
        mixed_route_root=mixed_root,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        v12_root=v12_root,
        targets=targets,
    )

    assert report["targets"][0]["classification"] == "full_span_generated_after_v12_seed"


def test_full_span_and_short_are_traced_independently(tmp_path: Path) -> None:
    root, mixed_root, stage_e_root, historical_root, v12_root, targets = _fixture(
        tmp_path, seed_boxes=[[10, 50, 14, 110]]
    )

    report = build_report(
        main_repo_root=root,
        mixed_route_root=mixed_root,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        v12_root=v12_root,
        targets=targets,
    )

    seed = report["targets"][0]["stages"]["historical_v12_seed"]
    assert seed["exact_full_span_present"] is False
    assert seed["exact_short_present"] is True


def test_report_records_selected_seed_and_all_stage_paths(tmp_path: Path) -> None:
    root, mixed_root, stage_e_root, historical_root, v12_root, targets = _fixture(
        tmp_path, seed_boxes=[[10, 10, 14, 110]]
    )

    report = build_report(
        main_repo_root=root,
        mixed_route_root=mixed_root,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        v12_root=v12_root,
        targets=targets,
    )

    target = report["targets"][0]
    assert target["historical_seed_resolution"]["path"].endswith(
        "Score/page_001/pipeline2_no_peak_candidates.json"
    )
    assert target["stages"]["historical_final_scored"]["path"].endswith(
        "pipeline2_no_peak_scored.json"
    )
    assert target["stages"]["historical_final_scored"]["candidate_count"] == 2
    assert target["stages"]["current_probe_rescue"]["path"].endswith(
        "eval2_Score_page_001/pipeline2_no_peak_candidates.json"
    )
