import json
from pathlib import Path

import pytest

from src.pipeline.detection.orchestrator import DetectorOrchestrator


def _orchestrator(
    tmp_path: Path,
    detection: dict,
    *,
    dry_run: bool = False,
) -> DetectorOrchestrator:
    return DetectorOrchestrator(
        config={"detection": detection},
        images=[],
        run_id="contract-test",
        run_dir=tmp_path,
        dry_run=dry_run,
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


def test_run_detection_returns_persisted_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _orchestrator(tmp_path, {})
    hybrid_output_dir = tmp_path / "hybrid"
    probe_output_dir = tmp_path / "probe"
    monkeypatch.setattr(
        orchestrator,
        "_run_hybrid_detection",
        lambda: {"hybrid_output_dir": hybrid_output_dir, "commands": []},
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_probe_scan",
        lambda: {"probe_output_dir": probe_output_dir, "commands": []},
    )
    monkeypatch.setattr(orchestrator, "_run_cnn_scoring", lambda: {"commands": []})

    result = orchestrator.run_detection()

    expected_path = tmp_path / "intermediate" / "detector_input_contract.json"
    assert result["detector_input_contract"] == orchestrator.input_contract
    assert result["detector_input_contract_path"] == expected_path
    assert expected_path.is_file()


def test_dry_run_returns_contract_without_writing_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _orchestrator(tmp_path, {}, dry_run=True)
    monkeypatch.setattr(
        orchestrator,
        "_run_hybrid_detection",
        lambda: {"hybrid_output_dir": tmp_path / "hybrid", "commands": []},
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_probe_scan",
        lambda: {"probe_output_dir": tmp_path / "probe", "commands": []},
    )
    monkeypatch.setattr(orchestrator, "_run_cnn_scoring", lambda: {"commands": []})

    result = orchestrator.run_detection()

    assert result["detector_input_contract"] == orchestrator.input_contract
    assert result["detector_input_contract_path"] is None
    assert not orchestrator.input_contract_path.exists()


@pytest.mark.parametrize(
    ("key", "resolver_name"),
    [
        ("precomputed_probe_candidates_root", "_resolve_precomputed_probe_candidates_root"),
        ("cnn_bands_from", "_resolve_cnn_bands_from"),
    ],
)
def test_true_is_not_a_valid_path_override(
    tmp_path: Path,
    key: str,
    resolver_name: str,
) -> None:
    orchestrator = _orchestrator(tmp_path, {key: True})
    orchestrator.hybrid_output_dir = tmp_path / "hybrid"

    with pytest.raises(TypeError):
        getattr(orchestrator, resolver_name)()
