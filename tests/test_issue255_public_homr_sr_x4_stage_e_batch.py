from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.issue255.prepare_public_homr_sr_x4_stage_e_batch import build_batch


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_batch_replaces_only_hybrid_runtime_artifact(tmp_path: Path) -> None:
    old_hybrid = tmp_path / "old_hybrid.json"
    restored_hybrid = tmp_path / "restored_hybrid.json"
    baseline = tmp_path / "baseline.json"
    old_hybrid.write_text("[]\n", encoding="utf-8")
    restored_hybrid.write_text("[[1, 2, 3, 4]]\n", encoding="utf-8")
    baseline.write_text("[[10, 20, 30, 40]]\n", encoding="utf-8")

    source_batch = tmp_path / "source_batch.json"
    _write_json(
        source_batch,
        {
            "schema_version": "source.v1",
            "status": "completed",
            "variant": "public_baseline",
            "runs": [
                {
                    "label": "page_a",
                    "contract": {
                        "status": "completed",
                        "artifacts": {
                            "fresh_baseline": {"path": str(baseline)},
                            "hybrid": {"path": str(old_hybrid), "sha256": "old"},
                        },
                    },
                }
            ],
        },
    )
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "status": "completed",
            "historical_artifact_used_as_runtime_input": False,
            "source_public_batch": str(source_batch),
            "summary": {"all_recomputed_hybrids_exact_historical": True},
            "pages": {"page_a": {"recomputed_hybrid": str(restored_hybrid)}},
        },
    )

    batch = build_batch(report)

    contract = batch["runs"][0]["contract"]
    assert contract["artifacts"]["fresh_baseline"]["path"] == str(baseline)
    assert contract["artifacts"]["hybrid"]["path"] == str(restored_hybrid.resolve())
    assert contract["artifacts"]["hybrid"]["sha256"] == hashlib.sha256(
        restored_hybrid.read_bytes()
    ).hexdigest()
    assert contract["issue255_stage_e_hybrid_override"][
        "historical_artifact_used_as_runtime_input"
    ] is False
    assert batch["historical_artifact_used_as_runtime_input"] is False
    assert batch["variant"] == "public_baseline"


def test_build_batch_requires_exact_restored_hybrid_gate(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "status": "completed",
            "historical_artifact_used_as_runtime_input": False,
            "summary": {"all_recomputed_hybrids_exact_historical": False},
        },
    )

    with pytest.raises(ValueError, match="not exact historical matches"):
        build_batch(report)
