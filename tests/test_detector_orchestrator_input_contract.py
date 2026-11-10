"""Detector input-contract behavior of the single dense detector route (#522)."""

import json
from pathlib import Path

import pytest

from src.pipeline.detection.dense_orchestrator_batch_sr import DetectorOrchestrator


def _orchestrator(
    tmp_path: Path,
    detection: dict | None = None,
    *,
    dry_run: bool = False,
    in_memory_images: dict | None = None,
) -> DetectorOrchestrator:
    det = {"homr_profile": "maintained_original", **(detection or {})}
    return DetectorOrchestrator(
        config={"detection": det},
        images=[],
        run_id="contract-test",
        run_dir=tmp_path,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )


def _stub_stages(orchestrator: DetectorOrchestrator, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_run_hybrid_detection",
        lambda: {"hybrid_output_dir": tmp_path / "hybrid", "commands": []},
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_dense_route",
        lambda: {"probe_output_dir": tmp_path / "probe", "commands": []},
    )
    monkeypatch.setattr(orchestrator, "_run_cnn_scoring", lambda: {"commands": []})


def test_omitted_route_records_fresh_dense_contract(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)

    path = orchestrator._record_input_contract()

    assert path == tmp_path / "intermediate" / "detector_input_contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mode"] == "fresh_upstream"
    assert payload["fresh_upstream_authoritative"] is True
    assert payload["override_keys"] == []
    assert payload["detector_route"] == "dense_full_pipeline"


def test_candidate_source_overrides_are_rejected_not_ignored(tmp_path: Path) -> None:
    # The former standard route consumed these; the dense route must not record and
    # then silently ignore them. Precomputed candidates belong to dense_probe_candidate_route.
    with pytest.raises(ValueError, match="precomputed_probe_candidates_root, cnn_bands_from"):
        _orchestrator(
            tmp_path,
            {
                "precomputed_probe_candidates_root": "logs/checkpoint/probe",
                "cnn_bands_from": "logs/checkpoint/bands",
            },
        )


def test_run_detection_returns_persisted_contract(tmp_path: Path, monkeypatch) -> None:
    orchestrator = _orchestrator(tmp_path)
    _stub_stages(orchestrator, monkeypatch, tmp_path)

    result = orchestrator.run_detection()

    expected_path = tmp_path / "intermediate" / "detector_input_contract.json"
    assert result["detector_input_contract"] == orchestrator.input_contract
    assert result["detector_input_contract_path"] == expected_path
    assert result["detector_route"] == "dense_full_pipeline"
    assert expected_path.is_file()


def test_dry_run_returns_contract_without_writing_manifest(tmp_path: Path, monkeypatch) -> None:
    orchestrator = _orchestrator(tmp_path, dry_run=True)
    _stub_stages(orchestrator, monkeypatch, tmp_path)

    result = orchestrator.run_detection()

    assert result["detector_input_contract"] == orchestrator.input_contract
    assert result["detector_input_contract_path"] is None
    assert not orchestrator.input_contract_path.exists()


def test_in_memory_images_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="persisted image files"):
        _orchestrator(tmp_path, in_memory_images={"page_001": object()})
