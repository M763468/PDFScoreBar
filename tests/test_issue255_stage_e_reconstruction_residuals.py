from __future__ import annotations

import json
from pathlib import Path

from tools.issue255.analyze_stage_e_reconstruction_residuals import build_report


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _record(path: Path) -> dict[str, object]:
    return {"path": str(path), "exists": True}


def test_build_report_traces_residuals_without_inference(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    accepted = _write(run_root / "accepted.json", [[0, 0, 4, 100], [10, 0, 14, 100]])
    control = _write(run_root / "control.json", [[0, 0, 4, 100]])
    raw = _write(
        run_root / "raw.json",
        [[0, 0, 4, 100], [10, 0, 14, 100], [30, 0, 34, 100]],
    )
    filtered = _write(run_root / "filtered.json", json.loads(raw.read_text()))
    issue53 = _write(run_root / "issue53.json", json.loads(raw.read_text()))
    scored = _write(
        run_root / "scored.json",
        [
            {"bbox": [0, 0, 4, 100], "score": 0.9},
            {"bbox": [30, 0, 34, 100], "score": 0.8},
        ],
    )
    final = _write(run_root / "final.json", [[0, 0, 4, 100], [30, 0, 34, 100]])
    suggestions = _write(run_root / "suggestions.json", {"drop_suggested": []})
    page = {
        "score": "Score",
        "page": "page_001",
        "accepted_reference": _record(accepted),
        "artifacts": {
            "control_final": _record(control),
            "dense_raw": _record(raw),
            "filtered": _record(filtered),
            "filter_suggestions": _record(suggestions),
            "issue53": _record(issue53),
            "cnn_scored": _record(scored),
            "cnn_accepted": _record(final),
        },
    }
    _write(
        run_root / "focused_stage_e_reconstruction_report.json",
        {
            "status": "completed",
            "repository": {"commit": "abc"},
            "gates": {"historical_runtime_artifact_dependency_absent": True},
            "pages": {"sample": page},
        },
    )

    report = build_report(run_root)

    sample = report["pages"]["sample"]
    assert sample["control_metrics"] == {"tp": 1, "fp": 0, "fn": 1}
    assert sample["reconstructed_metrics"] == {"tp": 1, "fp": 1, "fn": 1}
    assert sample["false_negative_residuals"][0]["accepted_bbox"] == [10, 0, 14, 100]
    assert sample["false_negative_residuals"][0]["first_loss_boundary"] == "cnn_scored"
    assert sample["false_positive_residuals"][0]["prediction_bbox"] == [30, 0, 34, 100]
    assert sample["false_positive_residuals"][0]["cnn_score"] == 0.8
    assert report["next_gpu_run_required"] is False
