from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.issue245.analyze_detector_fn_stages import _candidate_path, build_report


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_report_identifies_filter_loss_and_rescue_loss(tmp_path: Path) -> None:
    score = "Score"
    page = "page_004"
    target_a = (847, 2490, 854, 2591)
    target_b = (847, 2675, 854, 2776)
    stage_e_root = tmp_path / "stage_e_full_pipeline"
    dense_root = stage_e_root / "dense_candidate_reconstruction"
    historical_root = tmp_path / "historical"

    hybrid_path = _write_json(tmp_path / "mixed" / "hybrid.json", [])
    inventory_path = _write_json(
        tmp_path / "mixed_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "image": str(tmp_path / "page.png"),
                    "hybrid_predictions": str(hybrid_path),
                    "staff_mask": None,
                }
            ]
        },
    )

    raw = [list(target_a), list(target_b)]
    filtered = [list(target_a)]
    rescue: list[list[int]] = []
    _write_json(
        dense_root
        / "probe_candidates_from_inventory"
        / score
        / page
        / "pipeline2_no_peak_candidates.json",
        raw,
    )
    _write_json(
        dense_root
        / "probe_candidates_filtered"
        / score
        / page
        / "pipeline2_no_peak_candidates.json",
        filtered,
    )
    _write_json(
        dense_root
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_candidates.json",
        rescue,
    )
    _write_json(
        stage_e_root / score / page / "pipeline2_no_peak_candidates.json",
        rescue,
    )
    _write_json(
        historical_root / score / page / "pipeline2_no_peak_candidates.json",
        [list(target_a), list(target_b)],
    )
    _write_json(
        dense_root / "filter_suggestions" / score / f"{page}_suggestion.json",
        {
            "keep": [{"bbox": list(target_a), "reasons": []}],
            "drop_suggested": [{"bbox": list(target_b), "reasons": ["no_staff_overlap"]}],
        },
    )

    report = build_report(
        inventory_path=inventory_path,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        score=score,
        page=page,
        targets=[target_a, target_b],
    )

    first, second = report["targets"]
    assert first["trace"]["first_lost_transition"] == {
        "from": "filtered_dense_candidates",
        "to": "probe_rescue_candidates",
        "change": "lost",
    }
    assert second["trace"]["first_lost_transition"] == {
        "from": "raw_dense_candidates",
        "to": "filtered_dense_candidates",
        "change": "lost",
    }
    assert second["filter_decisions"][0]["disposition"] == "drop_suggested"
    assert second["filter_decisions"][0]["reasons"] == ["no_staff_overlap"]
    assert first["stages"]["historical_candidates"]["present"] is True
    assert second["stages"]["final_candidates"]["present"] is False
    assert report["inputs"]["stage_paths"]["probe_rescue_candidates"] == str(
        dense_root
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_candidates.json"
    )


def test_candidate_path_resolves_standard_layout(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "Score" / "page_004" / "pipeline2_no_peak_candidates.json", [])

    assert _candidate_path(tmp_path, "Score", "page_004") == path


def test_candidate_path_rejects_ambiguous_recursive_matches(tmp_path: Path) -> None:
    _write_json(tmp_path / "first" / "Score" / "page_004" / "pipeline2_no_peak_candidates.json", [])
    _write_json(
        tmp_path / "second" / "Score" / "page_004" / "pipeline2_no_peak_candidates.json", []
    )

    with pytest.raises(RuntimeError, match="Ambiguous"):
        _candidate_path(tmp_path, "Score", "page_004")


def test_build_report_traces_first_exact_geometry_loss(tmp_path: Path) -> None:
    score = "Score"
    page = "page_013"
    target = (100, 100, 104, 200)
    short = (100, 150, 104, 200)
    stage_e_root = tmp_path / "stage_e_full_pipeline"
    dense_root = stage_e_root / "dense_candidate_reconstruction"
    historical_root = tmp_path / "historical"
    hybrid_path = _write_json(tmp_path / "mixed" / "hybrid.json", [list(target)])
    inventory_path = _write_json(
        tmp_path / "mixed_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "image": str(tmp_path / "page.png"),
                    "hybrid_predictions": str(hybrid_path),
                    "staff_mask": None,
                }
            ]
        },
    )
    for layer, boxes in {
        "probe_candidates_from_inventory": [list(target)],
        "probe_candidates_filtered": [list(short)],
    }.items():
        _write_json(dense_root / layer / score / page / "pipeline2_no_peak_candidates.json", boxes)
    _write_json(
        dense_root
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_candidates.json",
        [list(short)],
    )
    _write_json(stage_e_root / score / page / "pipeline2_no_peak_candidates.json", [list(short)])
    _write_json(
        historical_root / score / page / "pipeline2_no_peak_candidates.json", [list(target)]
    )

    report = build_report(
        inventory_path=inventory_path,
        stage_e_root=stage_e_root,
        historical_root=historical_root,
        score=score,
        page=page,
        targets=[target],
    )

    target_report = report["targets"][0]
    assert target_report["historical_reference"]["bbox"] == list(target)
    assert (
        target_report["historical_reference"]["stage_comparisons"]["raw_dense_candidates"][
            "exact_present"
        ]
        is True
    )
    assert target_report["historical_geometry_trace"]["first_exact_loss_transition"] == {
        "from": "raw_dense_candidates",
        "to": "filtered_dense_candidates",
        "change": "lost",
    }
    assert target_report["historical_geometry_trace"]["first_shorter_matching_stage"] == (
        "filtered_dense_candidates"
    )
    assert target_report["historical_geometry_trace"]["first_shorter_matching_bbox"] == list(short)
