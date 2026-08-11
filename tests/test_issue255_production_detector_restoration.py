import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import yaml

import src.pipeline.detection.current_homr_worker as homr_worker
import src.pipeline.detection.current_sr_worker as sr_worker
import src.pipeline.detection.current_support_worker as support_worker
import src.pipeline.detection.profile_hybrid as profile_hybrid
import src.pipeline.detection.restored_orchestrator as restored
from src.pipeline.detection.input_contract import build_detector_input_contract


ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    return {
        "detection": {
            "enable_sr": True,
            "sr_scale": 4,
            "homr_profile": "stage_e_verified",
            "detector_route": "dense_full_pipeline",
            "probe_use_original_images": True,
            "cnn_model_path": "model.pth",
            "cnn_threshold": 0.1,
            "cnn_apply_nms": False,
        }
    }


def test_canonical_detector_config_uses_verified_restored_route() -> None:
    config = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text(encoding="utf-8"))
    detection = config["detection"]

    assert detection["enable_sr"] is True
    assert detection["sr_scale"] == 4
    assert detection["homr_profile"] == "stage_e_verified"
    assert detection["detector_route"] == "dense_full_pipeline"
    assert "execution_mode" not in detection
    assert detection["probe_use_original_images"] is True
    assert detection["cnn_threshold"] == 0.1
    assert detection["cnn_apply_nms"] is False
    assert detection.get("precomputed_probe_candidates_root") is None
    assert detection.get("cnn_bands_from") is None
    assert "rescue_low_paper_verticals" not in detection.get("candidate_filter_kwargs", {})

    contract = build_detector_input_contract(detection)
    assert contract["mode"] == "fresh_upstream"
    assert contract["fresh_upstream_authoritative"] is True
    assert contract["override_keys"] == []
    assert contract["detector_route"] == "dense_full_pipeline"
    assert contract["homr_profile"] == "stage_e_verified"
    assert contract["sr_scale"] == 4
    assert contract["probe_use_original_images"] is True


def test_verified_profile_is_selected_for_hybrid_detection(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    captured = {}

    class FakeProfileDetector:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            return {"commands": [["profile"]], "hybrid_output_dir": tmp_path / "hybrid"}

    monkeypatch.setattr(restored, "VerifiedProfileHybridDetector", FakeProfileDetector)
    orchestrator = restored.DetectorOrchestrator(
        config=_config(),
        images=[image],
        run_id="test",
        run_dir=tmp_path / "run",
        dry_run=False,
    )

    result = orchestrator._run_hybrid_detection()

    assert captured["profile_name"] == "stage_e_verified"
    assert captured["images"] == [image]
    assert result["commands"] == [["profile"]]


def test_current_sr_worker_uses_verified_x4_settings(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    output = tmp_path / "out/sr/batch/page_001/page_001.png"
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(
        json.dumps(
            {
                "detection": {
                    "sr_scale": 4,
                    "sr_tile": -1,
                    "sr_tile_pad": 10,
                    "sr_fp32": False,
                },
                "image": str(image),
                "output": str(output),
            }
        ),
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(sr_worker, "load_image", lambda _image, _cache: object())

    def fake_sr(_image, **kwargs):
        captured.update(kwargs)
        return object(), object()

    def fake_imwrite(path, _image):
        Path(path).write_bytes(b"sr")
        return True

    monkeypatch.setattr(sr_worker, "apply_advanced_sr", fake_sr)
    monkeypatch.setattr(sr_worker.cv2, "imwrite", fake_imwrite)

    sr_worker.run(request, result)
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert captured == {
        "model_name": "RealESRGAN_x4plus",
        "scale": 4,
        "tile": -1,
        "tile_pad": 10,
        "fp32": False,
        "upsampler": None,
    }
    assert payload["sr_scale"] == 4
    assert payload["historical_detector_artifact_runtime_input"] is False
    assert payload["sr_sha256"]
    assert output.is_file()


def test_current_homr_worker_is_lightweight_until_run() -> None:
    assert callable(homr_worker.run)
    assert callable(homr_worker.main)


def test_current_support_runs_sr_homr_omr_as_separate_phases(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    output_root = tmp_path / "support"
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(
        json.dumps(
            {
                "detection": {"sr_scale": 4},
                "image": str(image),
                "output_root": str(output_root),
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_child_worker(*, name, request, **_kwargs):
        if name == "Current x4 SR":
            calls.append("sr")
            sr = output_root / "sr/batch/page_001/page_001.png"
            sr.parent.mkdir(parents=True)
            sr.write_bytes(b"sr")
            return (
                {
                    "status": "completed",
                    "sr_image": str(sr),
                    "sr_sha256": "abc",
                    "historical_detector_artifact_runtime_input": False,
                },
                ["python", "current_sr_worker"],
            )
        if name == "Current HOMR on x4":
            calls.append("homr")
            assert Path(request["sr_image"]).is_file()
            homr_root = Path(request["output_root"]) / "batch/page_001"
            homr_root.mkdir(parents=True)
            detection = homr_root / "page_001_detections.json"
            staff = homr_root / "page_001_staff_mask.png"
            symbols = homr_root / "page_001_connector_symbols.png"
            brace = homr_root / "page_001_connector_brace_dot.png"
            for path in (detection, staff, symbols, brace):
                path.write_bytes(b"artifact")
            return (
                {
                    "status": "completed",
                    "current_sr_detection": str(detection),
                    "staff_mask": str(staff),
                    "connector_symbols": str(symbols),
                    "connector_brace_dot": str(brace),
                    "historical_detector_artifact_runtime_input": False,
                },
                ["python", "current_homr_worker"],
            )
        raise AssertionError(name)

    def fake_pipeline_python(name):
        assert name == "omr_dln"
        return ["python"]

    def fake_run(command, **_kwargs):
        calls.append("omr")
        assert "--pre-computed-sr" in command
        omr = output_root / "omr_sr/page_001/predictions.json"
        omr.parent.mkdir(parents=True)
        omr.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(support_worker, "_run_child_worker", fake_child_worker)
    monkeypatch.setattr(support_worker, "get_pipeline_python", fake_pipeline_python)
    monkeypatch.setattr(support_worker, "run_with_logging", fake_run)

    support_worker.run(request, result)
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert calls == ["sr", "homr", "omr"]
    assert payload["schema_version"] == "pipeline.current_x4_support.v3"
    assert payload["current_homr_executed"] is True
    assert payload["memory_phase_boundaries"] == ["sr", "current_homr", "omr_dln"]
    assert payload["sr_sha256"] == "abc"
    assert Path(payload["sr_image"]).is_file()
    assert Path(payload["current_sr_detection"]).is_file()
    assert Path(payload["connector_symbols"]).is_file()
    assert Path(payload["connector_brace_dot"]).is_file()
    assert Path(payload["current_omr"]).is_file()
    assert payload["historical_detector_artifact_runtime_input"] is False


def test_verified_profile_collects_current_support_per_page(tmp_path: Path, monkeypatch) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    images = [score / "page_001.png", score / "page_002.png"]
    for image in images:
        image.write_bytes(b"image")

    detector = profile_hybrid.VerifiedProfileHybridDetector(
        det_cfg=_config()["detection"],
        images=images,
        run_id="test",
        project_root=tmp_path,
        dry_run=False,
        skip_existing=False,
        profile_name="stage_e_verified",
    )
    calls = []

    def fake_support(*, image: Path, output_root: Path):
        calls.append(image)
        artifacts = output_root / image.parent.name / image.stem / "artifacts"
        sr = artifacts / "sr" / "batch" / image.stem / image.name
        omr = artifacts / "omr_sr" / image.stem / "predictions.json"
        sr.parent.mkdir(parents=True)
        omr.parent.mkdir(parents=True)
        sr.write_bytes(b"sr")
        omr.write_text("[]\n", encoding="utf-8")
        return (
            {
                "status": "completed",
                "sr_image": str(sr),
                "current_omr": str(omr),
                "historical_detector_artifact_runtime_input": False,
            },
            ["support-worker", str(image)],
        )

    monkeypatch.setattr(detector, "_support_worker", fake_support)

    sr_images, omr_predictions, commands = detector._generate_current_support(tmp_path / "out")

    assert calls == images
    assert list(sr_images) == images
    assert list(omr_predictions) == images
    assert len(commands) == 2


def test_dense_inventory_uses_only_current_hybrid_and_profile_masks(tmp_path: Path) -> None:
    image = tmp_path / "Score" / "page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    run_dir = tmp_path / "run"
    orchestrator = restored.DetectorOrchestrator(
        config=_config(),
        images=[image],
        run_id="test",
        run_dir=run_dir,
        dry_run=False,
    )

    hybrid_root = tmp_path / "hybrid"
    baseline_page = hybrid_root / "baseline/batch/page_001"
    baseline_page.mkdir(parents=True)
    staff = baseline_page / "page_001_proxy_debug_3_staff.png"
    clef = baseline_page / "page_001_proxy_debug_7_clefs_keys.png"
    staff.write_bytes(b"staff")
    clef.write_bytes(b"clef")
    hybrid = hybrid_root / "hybrid_results/page_001_hybrid.json"
    hybrid.parent.mkdir(parents=True)
    hybrid.write_text("[]\n", encoding="utf-8")
    orchestrator.hybrid_output_dir = hybrid_root

    inventory_path, exclude_path = orchestrator._write_dense_inventory()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    assert inventory["historical_detector_artifact_runtime_input"] is False
    assert inventory["records"] == [
        {
            "score": "Score",
            "page": "page_001",
            "image": str(image.resolve()),
            "hybrid_predictions": str(hybrid.resolve()),
            "staff_mask": str(staff.resolve()),
            "clef_mask": str(clef.resolve()),
            "run_dir": str(baseline_page.resolve()),
        }
    ]
    assert json.loads(exclude_path.read_text(encoding="utf-8")) == {"excluded_pages": []}


def test_dense_route_cnn_uses_original_coordinates_and_nms_false(
    tmp_path: Path, monkeypatch
) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    model = tmp_path / "model.pth"
    model.write_bytes(b"model")
    config = _config()
    config["detection"]["cnn_model_path"] = str(model)
    orchestrator = restored.DetectorOrchestrator(
        config=config,
        images=[image],
        run_id="test",
        run_dir=tmp_path / "run",
        dry_run=False,
    )
    filtered = tmp_path / "filtered"
    probe = tmp_path / "probe"
    filtered.mkdir()
    probe.mkdir()
    orchestrator._dense_route = SimpleNamespace(
        filtered_root=filtered,
        probe_rescue_root=probe,
        execution_summary={},
    )
    orchestrator.probe_output_dir = probe
    captured = {}

    def fake_score(**kwargs):
        captured.update(kwargs)
        return 1

    fake_cnn = types.ModuleType("src.pipeline.steps.cnn_scoring")
    fake_cnn.run_cnn_scoring_batch = fake_score
    monkeypatch.setitem(sys.modules, "src.pipeline.steps.cnn_scoring", fake_cnn)

    orchestrator._run_cnn_scoring()

    assert captured["images"] == [image]
    assert captured["input_image_scale"] == 1.0
    assert captured["bands_from"] == filtered
    assert captured["apply_nms_enabled"] is False
