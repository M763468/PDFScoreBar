from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.core.manifest import build_manifest
from tools.issue264.phase_b_page001_acceptance import target_manifest_entry


def test_manifest_records_mmr_geometry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.pipeline.core.manifest.describe_connector_artifacts",
        lambda _path: {"available": False},
    )
    provenance = {
        "staff_mask": "fresh_staff.png",
        "producer": "HybridDetector._run_homr_in_process",
        "producer_runtime": "current_pipeline_homr",
        "historical_detector_artifact_runtime_input": False,
    }
    manifest = build_manifest(
        {},
        run_id="test",
        run_dir=tmp_path,
        images=[tmp_path / "page.png"],
        page_ids=["page_001"],
        page_runs=["page_001"],
        resolved=[
            {
                "barlines_json": "barlines.json",
                "staff_mask": "proxy_staff.png",
                "mmr_staff_geometry": provenance,
            }
        ],
        commands=[],
        page_statuses=[],
        barline_override_stats={},
    )

    assert manifest["pages"][0]["staff_mask"] == "proxy_staff.png"
    assert manifest["pages"][0]["mmr_geometry"] == provenance


def test_acceptance_target_entry_supports_composite_stem() -> None:
    entry = {
        "page_id": "Va_Prokofiev_Symphony1_page_001",
        "image_path": "/workspace/data/Va_Prokofiev_Symphony1_page_001.png",
    }
    assert target_manifest_entry({"pages": [entry]}) is entry
