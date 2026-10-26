from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.common.model_artifacts import ModelArtifactIntegrityError
from src.pipeline.detection import dense_orchestrator as dense
from src.pipeline.detection.model_selection import (
    model_observation,
    model_validation_mode,
    resolve_cnn_candidate,
    resolve_omr_model,
)


def _candidate_config(tmp_path):
    cnn = tmp_path / "candidate.pth"
    omr = tmp_path / "candidate.pt"
    cnn.write_bytes(b"cnn v1")
    omr.write_bytes(b"omr v1")
    return {
        "model_validation": "exploration",
        "cnn_model_path": str(cnn),
        # Copied production manifest must not shadow an explicit research path.
        "cnn_model_manifest": "models/barline_cnn/manifest.json",
        "omr_dln_model_path": str(omr),
        "cnn_threshold": 0.2,
        "cnn_apply_nms": False,
        "homr_profile": "maintained_original",
        "detector_route": "dense_full_pipeline",
        "cnn_device": "cpu",
        "probe_skip_existing": True,
    }


def test_exploration_observes_repeated_replacement_without_registration(tmp_path):
    cfg = _candidate_config(tmp_path)
    first = model_observation(cfg, tmp_path)
    Path(cfg["cnn_model_path"]).write_bytes(b"cnn v2")
    Path(cfg["omr_dln_model_path"]).write_bytes(b"omr v2")
    second = model_observation(cfg, tmp_path)
    assert first["cnn"]["sha256"] != second["cnn"]["sha256"]
    assert first["omr_dln"]["sha256"] != second["omr_dln"]["sha256"]
    assert not (tmp_path / "models").exists()


def test_missing_explicit_candidate_never_falls_back_to_manifest(tmp_path):
    cfg = _candidate_config(tmp_path)
    Path(cfg["cnn_model_path"]).unlink()
    with pytest.raises(FileNotFoundError):
        resolve_cnn_candidate(cfg, tmp_path)
    Path(cfg["omr_dln_model_path"]).unlink()
    with pytest.raises(FileNotFoundError):
        resolve_omr_model(cfg, tmp_path)


def test_comparison_freezes_observed_bytes_only_when_requested(tmp_path):
    cfg = _candidate_config(tmp_path)
    observed = model_observation(cfg, tmp_path)
    cfg["model_validation"] = "comparison"
    with pytest.raises(ValueError, match="model_sha256"):
        model_observation(cfg, tmp_path)
    cfg["model_sha256"] = {role: item["sha256"] for role, item in observed.items()}
    assert model_observation(cfg, tmp_path) == observed
    Path(cfg["omr_dln_model_path"]).write_bytes(b"updated")
    with pytest.raises(ModelArtifactIntegrityError):
        model_observation(cfg, tmp_path)


def test_production_omr_override_still_requires_selected_sha(tmp_path):
    cfg = _candidate_config(tmp_path)
    cfg["model_validation"] = "production"
    manifest = tmp_path / "models/omr_dln/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "pdfscorebar.model_artifact.v1",
                "model_id": "omr",
                "version": "selected",
                "architecture": "yolo",
                "distribution": {"mode": "operator-supplied", "asset": "model.pt"},
                "sha256": hashlib.sha256(b"selected").hexdigest(),
                "cache_path": "omr/model.pt",
            }
        )
    )
    with pytest.raises(ModelArtifactIntegrityError):
        resolve_omr_model(cfg, tmp_path)
    Path(cfg["omr_dln_model_path"]).write_bytes(b"selected")
    assert resolve_omr_model(cfg, tmp_path) == Path(cfg["omr_dln_model_path"])


def test_unknown_mode_is_rejected():
    assert model_validation_mode({}) == "production"
    with pytest.raises(ValueError, match="Unknown"):
        model_validation_mode({"model_validation": "skip"})


def test_candidate_runs_use_explicit_path_threshold_and_device(tmp_path, monkeypatch):
    cfg = _candidate_config(tmp_path)
    orchestrator = dense.DetectorOrchestrator(
        config={"detection": cfg},
        images=[],
        run_id="test",
        run_dir=tmp_path / "run",
        dry_run=False,
    )
    assert orchestrator.skip_existing is False
    orchestrator._dense_route = SimpleNamespace(filtered_root=tmp_path, probe_rescue_root=tmp_path)
    orchestrator.probe_output_dir = tmp_path
    calls = []
    monkeypatch.setattr(
        dense,
        "_resolve_verified_cnn_artifact",
        lambda *a, **k: pytest.fail("production validator called"),
    )
    import src.pipeline.steps.cnn_scoring as cnn

    monkeypatch.setattr(cnn, "run_cnn_scoring_batch", lambda **kw: calls.append(kw))
    orchestrator._run_cnn_scoring()
    Path(cfg["cnn_model_path"]).write_bytes(b"new checkpoint")
    orchestrator._run_cnn_scoring()
    assert len(calls) == 2
    assert calls[0]["model_path"] == Path(cfg["cnn_model_path"])
    assert calls[0]["threshold"] == 0.2
    assert calls[0]["device_name"] == "cpu"


@pytest.mark.parametrize("architecture", ["resnet18", "efficientnet_b0"])
def test_candidate_loader_accepts_supported_architectures_and_checks_io(tmp_path, architecture):
    import torch

    from src.pipeline.steps.cnn_scoring import _build_model, validate_cnn_candidate

    checkpoint = tmp_path / "candidate.pth"
    torch.save(_build_model(architecture).state_dict(), checkpoint)
    validate_cnn_candidate(checkpoint, "cpu")
    # Replacing bytes at the same path is a normal exploration operation.
    checkpoint.write_bytes(b"corrupt checkpoint")
    with pytest.raises(Exception):
        validate_cnn_candidate(checkpoint, "cpu")


def test_candidate_loader_rejects_incompatible_head(tmp_path):
    import torch

    from src.pipeline.steps.cnn_scoring import _build_model, validate_cnn_candidate

    model = _build_model("resnet18")
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    checkpoint = tmp_path / "candidate.pth"
    torch.save(model.state_dict(), checkpoint)
    with pytest.raises(RuntimeError, match="size mismatch"):
        validate_cnn_candidate(checkpoint, "cpu")


def test_requested_cuda_never_falls_back(tmp_path, monkeypatch):
    import torch

    from src.pipeline.detection.omr_dln_worker import load_candidate
    from src.pipeline.steps.cnn_scoring import _select_device

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="refusing CPU fallback"):
        _select_device("cuda")
    checkpoint = tmp_path / "candidate.pt"
    checkpoint.write_bytes(b"checkpoint")
    with pytest.raises(RuntimeError, match="refusing CPU fallback"):
        load_candidate(checkpoint, "cuda")


def test_omr_candidate_rejects_wrong_task(tmp_path, monkeypatch):
    from src.pipeline.detection.omr_dln_worker import load_candidate

    checkpoint = tmp_path / "candidate.pt"
    checkpoint.write_bytes(b"checkpoint")
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        SimpleNamespace(YOLO=lambda p: SimpleNamespace(task="classify", names={0: "measure"})),
    )
    with pytest.raises(ValueError, match="detection checkpoint"):
        load_candidate(checkpoint, "cpu")


def test_candidate_run_records_current_hashes_and_rejects_mid_run_changes(tmp_path, monkeypatch):
    cfg = _candidate_config(tmp_path)
    run_dir = tmp_path / "run"
    orchestrator = dense.DetectorOrchestrator(
        config={"detection": cfg},
        images=[],
        run_id="test",
        run_dir=run_dir,
        dry_run=False,
    )
    monkeypatch.setattr(
        orchestrator, "_run_hybrid_detection", lambda: {"hybrid_output_dir": tmp_path}
    )
    monkeypatch.setattr(orchestrator, "_run_dense_route", lambda: {"probe_output_dir": tmp_path})
    monkeypatch.setattr(orchestrator, "_run_cnn_scoring", lambda: {})
    orchestrator.run_detection()
    recorded = json.loads((run_dir / "model_selection.json").read_text())
    assert recorded["models"] == model_observation(cfg, tmp_path)
    assert recorded["status"] == "selected"  # Observation is not accuracy acceptance.

    def replace_during_scoring():
        Path(cfg["cnn_model_path"]).write_bytes(b"changed during scoring")
        return {}

    monkeypatch.setattr(orchestrator, "_run_cnn_scoring", replace_during_scoring)
    with pytest.raises(RuntimeError, match="results are invalid"):
        orchestrator.run_detection()


@pytest.mark.parametrize("key", ["cnn_device", "omr_dln_device"])
def test_candidate_device_must_be_explicit_supported_value(key):
    with pytest.raises(ValueError, match=key):
        model_validation_mode(
            {"model_validation": "exploration", "detector_route": "dense_full_pipeline", key: None}
        )


def test_production_threshold_contract_remains_required(tmp_path):
    from src.common.model_artifacts import load_model_artifact_manifest

    root = Path(__file__).resolve().parents[1]
    manifest = load_model_artifact_manifest(root / "models/barline_cnn/manifest.json")
    with pytest.raises(ValueError, match="threshold does not match"):
        dense._validate_verified_cnn_manifest(manifest, cnn_threshold=0.2)


def test_frozen_distribution_rejects_candidate_mode_before_loading(tmp_path, monkeypatch, capsys):
    import yaml

    from docker import runtime_contract

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "detection": {
                    "model_validation": "exploration",
                    "detector_route": "dense_full_pipeline",
                }
            }
        )
    )
    (tmp_path / runtime_contract.PROVENANCE_NAME).write_text("{}")
    monkeypatch.setattr(runtime_contract, "validate_distribution_provenance", lambda root: {})
    monkeypatch.setattr(runtime_contract, "runtime_fingerprint", lambda root: "matching")
    assert (
        runtime_contract.run_preflight(
            tmp_path, config, tmp_path / "missing", expected_fingerprint_value="matching"
        )
        == 2
    )
    assert "Frozen distributions require production" in capsys.readouterr().err


def test_cpu_candidate_probe_does_not_hide_runtime_cuda(tmp_path, monkeypatch, capsys):
    import os

    import onnxruntime
    import torch
    import yaml

    from docker import runtime_contract
    from src.common import model_artifacts
    from src.pipeline.detection import omr_dln_worker
    from src.pipeline.steps import cnn_scoring

    cfg = _candidate_config(tmp_path)
    cfg["omr_dln_device"] = "cpu"
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"detection": cfg}))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(runtime_contract, "runtime_fingerprint", lambda root: "matching")
    monkeypatch.setattr(runtime_contract, "_validate_production_provenance", lambda *args: None)
    monkeypatch.setattr(runtime_contract, "RUNTIME_MODULES", ())
    monkeypatch.setattr(
        model_artifacts,
        "resolve_realesrgan_weight",
        lambda *args, **kwargs: Path(cfg["cnn_model_path"]),
    )
    monkeypatch.setattr(cnn_scoring, "validate_cnn_candidate", lambda *args: None)
    monkeypatch.setattr(
        torch.cuda, "is_available", lambda: os.environ.get("CUDA_VISIBLE_DEVICES") != "-1"
    )
    monkeypatch.setattr(torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda device: "test GPU")
    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CUDAExecutionProvider"])

    class CpuCandidate:
        def predict(self, *args, **kwargs):
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            return [SimpleNamespace(boxes=[])]

    monkeypatch.setattr(omr_dln_worker, "load_candidate", lambda *args: CpuCandidate())
    assert (
        runtime_contract.run_preflight(
            tmp_path, config, tmp_path / "none", expected_fingerprint_value="matching"
        )
        == 0
    )
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"
    assert json.loads(capsys.readouterr().out)["cuda_device"] == "test GPU"


@pytest.mark.parametrize("mode", ["exploration", "comparison"])
@pytest.mark.parametrize("route", [None, "standard", "unsupported_route"])
def test_candidate_routes_are_rejected_before_standard_dispatch(tmp_path, monkeypatch, mode, route):
    import yaml

    from src.pipeline import detection
    from src.pipeline.main import run_pipeline

    cfg = _candidate_config(tmp_path)
    cfg["model_validation"] = mode
    if route is None:
        cfg.pop("detector_route")
    else:
        cfg["detector_route"] = route
    config = {"detection": cfg}
    monkeypatch.setattr(
        detection, "_install_standard_detector_hooks", lambda: pytest.fail("standard route entered")
    )
    message = "requires detector_route='dense_full_pipeline'"
    with pytest.raises(ValueError, match=message):
        detection.DetectorOrchestrator(config, [], "test", tmp_path / "run", dry_run=False)
    with pytest.raises(ValueError, match=message):
        detection.run_detection_step(config, [], [], "test", tmp_path / "run", dry_run=False)
    config_path = tmp_path / "candidate.yaml"
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match=message):
        run_pipeline(config_path, run_id="test", output_root=tmp_path)


@pytest.mark.parametrize("mode", ["exploration", "comparison"])
@pytest.mark.parametrize("route", [None, "standard", "unsupported_route"])
def test_preflight_rejects_candidate_routes_before_gpu_or_model_work(
    tmp_path, monkeypatch, capsys, mode, route
):
    import torch
    import yaml

    from docker import runtime_contract

    cfg = {"model_validation": mode}
    if route is not None:
        cfg["detector_route"] = route
    config = tmp_path / "candidate.yaml"
    config.write_text(yaml.safe_dump({"detection": cfg}))
    monkeypatch.setattr(runtime_contract, "runtime_fingerprint", lambda root: "matching")
    monkeypatch.setattr(
        torch.cuda, "is_available", lambda: pytest.fail("GPU probed before route validation")
    )
    monkeypatch.setattr(
        runtime_contract, "_require_file", lambda *a, **k: pytest.fail("asset work entered")
    )
    assert (
        runtime_contract.run_preflight(
            tmp_path, config, tmp_path / "none", expected_fingerprint_value="matching"
        )
        == 2
    )
    result = json.loads(capsys.readouterr().err)
    assert result["status"] == "fail"
    assert "requires detector_route='dense_full_pipeline'" in result["errors"][0]


@pytest.mark.parametrize("mode", ["exploration", "comparison"])
def test_supported_candidate_route_dispatch_preserves_selection(tmp_path, monkeypatch, mode):
    from src.pipeline import detection
    from src.pipeline.detection import dense_orchestrator_batch_sr

    cfg = _candidate_config(tmp_path)
    observed = model_observation(cfg, tmp_path)
    cfg["model_validation"] = mode
    if mode == "comparison":
        cfg["model_sha256"] = {role: model["sha256"] for role, model in observed.items()}
    config = {"detection": cfg}
    constructor = detection.DetectorOrchestrator(
        config, [], "test", tmp_path / "run", dry_run=False
    )
    assert isinstance(constructor, dense_orchestrator_batch_sr.DetectorOrchestrator)
    assert constructor.model_validation == mode

    def selected_model_run(config, *args, **kwargs):
        return model_observation(config["detection"], tmp_path)

    monkeypatch.setattr(dense_orchestrator_batch_sr, "run_detection_step", selected_model_run)
    assert (
        detection.run_detection_step(config, [], [], "test", tmp_path / "run", dry_run=False)
        == observed
    )
