import json
from pathlib import Path

import yaml

import src.pipeline.detection.restored_orchestrator as restored
from src.pipeline.detector_routes.dense_full_pipeline import DenseRouteArtifacts


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
    assert detection["probe_use_original_images"] is True
    assert detection["cnn_threshold"] == 0.1
    assert detection["cnn_apply_nms"] is False
    assert detection.get("precomputed_probe_candidates_root") is None
    assert detection.get("cnn_bands_from") is None
    assert "rescue_low_paper_verticals" not in detection.get("candidate_filter_kwargs", {})


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
