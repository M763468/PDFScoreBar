from __future__ import annotations

import json
from pathlib import Path

import tools.issue255.analyze_public_baseline_stage_e_residuals as analyzer


def test_fresh_contract_matches_required_fields_with_extra_metadata() -> None:
    assert analyzer._fresh_contract_matches(
        {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
            "schema_version": "pipeline.detector_input_contract.v1",
            "hybrid_detection_may_execute": True,
        }
    )


def test_fresh_contract_interpretation_distinguishes_old_and_fixed_runner() -> None:
    assert "older replay runner" in analyzer._fresh_contract_interpretation(False, True)
    assert "agrees" in analyzer._fresh_contract_interpretation(True, True)
    assert "disagree" in analyzer._fresh_contract_interpretation(True, False)


def test_build_report_adapts_public_pipeline_control(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    public_final = {"path": str(run_root / "public.json")}
    page = {
        "score": "Score",
        "page": "page_001",
        "accepted_reference": {"path": str(run_root / "accepted.json")},
        "artifacts": {
            "public_pipeline_final": public_final,
            "dense_raw": {"path": str(run_root / "raw.json")},
            "filtered": {"path": str(run_root / "filtered.json")},
            "filter_suggestions": {"path": str(run_root / "suggestions.json")},
            "issue53": {"path": str(run_root / "issue53.json")},
            "cnn_scored": {"path": str(run_root / "scored.json")},
            "cnn_accepted": {"path": str(run_root / "final.json")},
        },
        "source_contract": {
            "fresh_contract": {
                "mode": "fresh_upstream",
                "fresh_upstream_authoritative": True,
                "override_keys": [],
                "schema_version": "pipeline.detector_input_contract.v1",
            }
        },
    }
    public_report = {
        "status": "completed",
        "repository": {"commit": "abc"},
        "gates": {
            "fresh_contract_exact": False,
            "public_baselines_preserved": True,
            "upstream_gpu_rerun_performed": False,
            "historical_runtime_artifact_dependency_absent": True,
        },
        "pages": {"sample": page},
    }
    (run_root / analyzer.PUBLIC_REPORT_NAME).write_text(
        json.dumps(public_report),
        encoding="utf-8",
    )

    captured = {}

    def fake_build(temp_root: Path):
        compat = json.loads((temp_root / analyzer.COMPAT_REPORT_NAME).read_text(encoding="utf-8"))
        captured.update(compat)
        return {
            "status": "completed",
            "combined": {
                "control_metrics": {"tp": 1, "fp": 0, "fn": 1},
                "reconstructed_metrics": {"tp": 2, "fp": 1, "fn": 0},
                "delta": {"tp": 1, "fp": 1, "fn": -1},
            },
            "pages": {},
        }

    monkeypatch.setattr(analyzer, "_build_focused_report", fake_build)

    report = analyzer.build_report(run_root)

    assert captured["pages"]["sample"]["artifacts"]["control_final"] == public_final
    assert report["control_role"] == "public_pipeline_final"
    assert report["fresh_contract_gate"]["original_report_value"] is False
    assert report["fresh_contract_gate"]["required_fields_match"] is True
    assert "older replay runner" in report["fresh_contract_gate"]["interpretation"]
    assert report["next_gpu_run_required"] is False
