import json
from pathlib import Path

import yaml

import src.pipeline.detection.profile_hybrid as profile_hybrid
import src.pipeline.detection.restored_orchestrator as restored
from src.pipeline.detection.input_contract import build_detector_input_contract
from src.pipeline.detector_routes.dense_full_pipeline import DenseRouteArtifacts


ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    return {
        "detection": {
            "enable_sr": True,
            "sr_scale": 4,
            "homr_profile": "stage_e_verified",
            "detector_route": "dense_full_pipeline",
            "execution_mode": "isolated_per_page",
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
    assert detection["execution_mode"] == "isolated_per_page"
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
    assert contract["execution_mode"] == "isolated_per_page"
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


def test_verified_profile_uses_historical_sr_generation_settings(
    tmp_path: Path, monkeypatch
) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"image")
    detector = object.__new__(profile_hybrid.VerifiedProfileHybridDetector)
    detector.dry_run = False
    detector.images = [image]
    detector.in_memory_images = None
    detector.det_cfg = {"sr_tile": -1, "sr_tile_pad": 10, "sr_fp32": False}

    captured = {}
    upsampler = object()
    monkeypatch.setattr(profile_hybrid, "load_image", lambda _image, _cache: object())

    def fake_sr(_image, **kwargs):
        captured.update(kwargs)
        return object(), upsampler

    monkeypatch.setattr(profile_hybrid, "apply_advanced_sr", fake_sr)
    monkeypatch.setattr(profile_hybrid.cv2, "imwrite", lambda _path, _image: True)
    monkeypatch.setattr(profile_hybrid.gc, "collect", lambda: 0)
    monkeypatch.setattr(profile_hybrid.torch.cuda, "is_available", lambda: False)

    generated = detector._generate_sr_sources(tmp_path / "sr", sr_scale=4)

    assert generated == {image: tmp_path / "sr/batch/page_001/page_001.png"}
    assert captured["model_name"] == "RealESRGAN_x4plus"
    assert captured["scale"] == 4
    assert captured["tile"] == -1
    assert captured["tile_pad"] == 10
    assert captured["fp32"] is False
    assert captured["upsampler"] is None


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
    orchestrator._dense_route = DenseRouteArtifacts(
        image_paths=[image],
        filtered_root=filtered,
        probe_rescue_root=probe,
        execution_summary={},
    )
    orchestrator.probe_output_dir = probe
    captured = {}

    def fake_score(**kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(restored, "run_cnn_scoring_batch", fake_score)

    orchestrator._run_cnn_scoring()

    assert captured["images"] == [image]
    assert captured["input_image_scale"] == 1.0
    assert captured["bands_from"] == filtered
    assert captured["apply_nms_enabled"] is False
