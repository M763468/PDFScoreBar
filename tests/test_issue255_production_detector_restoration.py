import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import yaml

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


def test_current_support_worker_reuses_maintained_x4_homr_path(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    output_root = tmp_path / "support"
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(
            {
                "detection": {"sr_scale": 4},
                "image": str(image),
                "output_root": str(output_root),
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    class FakeHybridDetector:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def _run_homr_in_process(self, sr_output, *, enable_sr, sr_scale):
            captured["homr"] = {
                "output": sr_output,
                "enable_sr": enable_sr,
                "sr_scale": sr_scale,
            }
            page = sr_output / "batch/page_001"
            page.mkdir(parents=True)
            (page / "page_001.png").write_bytes(b"sr")
            (page / "page_001_detections.json").write_text("[]\n", encoding="utf-8")

        def _rel(self, path):
            return str(path)

        def _get_python_cmd(self, _name):
            return ["fake-python"]

    fake_hybrid = types.ModuleType("src.pipeline.detection.hybrid")
    fake_hybrid.HybridDetector = FakeHybridDetector
    monkeypatch.setitem(sys.modules, "src.pipeline.detection.hybrid", fake_hybrid)

    import src.pipeline.detection.connector_artifacts as connector_artifacts

    monkeypatch.setattr(
        connector_artifacts, "install_homr_connector_artifact_capture", lambda: True
    )
    monkeypatch.setattr(connector_artifacts, "install_homr_skip_existing_guard", lambda _cls: True)

    def fake_run(command, **_kwargs):
        captured["omr_command"] = list(command)
        omr = output_root / "omr_sr/page_001/predictions.json"
        omr.parent.mkdir(parents=True)
        omr.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(support_worker, "run_with_logging", fake_run)

    support_worker.run(request_path, result_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert captured["homr"]["enable_sr"] is True
    assert captured["homr"]["sr_scale"] == 4
    assert result["sr_scale"] == 4
    assert result["historical_detector_artifact_runtime_input"] is False
    assert Path(result["sr_image"]).is_file()
    assert Path(result["current_omr"]).is_file()
    assert "--pre-computed-sr" in captured["omr_command"]


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
