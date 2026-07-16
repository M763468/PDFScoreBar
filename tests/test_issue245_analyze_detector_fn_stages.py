from __future__ import annotations

import json
from pathlib import Path

from tools.issue245.analyze_detector_fn_stages import build_report


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
        / score
        / page
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
            "drop_suggested": [
                {"bbox": list(target_b), "reasons": ["no_staff_overlap"]}
            ],
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
