import json
from pathlib import Path

import pytest

pytest.importorskip("homr")

from src.pipeline.detection.orchestrator import DetectorOrchestrator


def _orchestrator(tmp_path: Path, detection: dict) -> DetectorOrchestrator:
    return DetectorOrchestrator(
        config={"detection": detection},
        images=[],
        run_id="contract-test",
        run_dir=tmp_path,
        dry_run=False,
    )


def test_orchestrator_records_fresh_upstream_contract(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, {})

    path = orchestrator._record_input_contract()

    assert path == tmp_path / "intermediate" / "detector_input_contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mode"] == "fresh_upstream"
    assert payload["fresh_upstream_authoritative"] is True
    assert payload["override_keys"] == []


def test_orchestrator_records_precomputed_candidate_contract(tmp_path: Path) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        {
            "precomputed_probe_candidates_root": "logs/checkpoint/probe",
            "cnn_bands_from": "logs/checkpoint/bands",
        },
    )

    path = orchestrator._record_input_contract()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mode"] == "precomputed_candidate_route"
    assert payload["fresh_upstream_authoritative"] is False
    assert payload["override_keys"] == [
        "precomputed_probe_candidates_root",
        "cnn_bands_from",
    ]
