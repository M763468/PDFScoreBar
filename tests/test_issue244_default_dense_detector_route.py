from __future__ import annotations

from pathlib import Path

from src.pipeline.detection import run_detection_step
from src.pipeline.detector_routes.dense_full_pipeline import DenseRouteArtifacts
from src.pipeline.detector_routes.production_dense import (
    DENSE_ROUTE_PROFILE,
    apply_dense_profile,
    normalize_runtime_detection_config,
    resolve_detector_route,
)


def test_dense_route_is_default_and_applies_canonical_profile() -> None:
    detection = {
        "enable_sr": False,
        "min_ratio": 0.7,
        "crop_recenter_on_bbox_ink": False,
    }

    route, selection = resolve_detector_route(detection)
    overwritten = apply_dense_profile(detection)

    assert route == "dense"
    assert selection == "default"
    assert detection["enable_sr"] is True
    assert detection["min_ratio"] == 0.6
    assert detection["crop_recenter_on_bbox_ink"] is True
    assert overwritten["enable_sr"] == {"configured": False, "effective": True}


def test_ordinary_route_requires_explicit_opt_out() -> None:
    route, selection = resolve_detector_route({"route": "ordinary", "enable_sr": False})

    assert route == "ordinary"
    assert selection == "explicit"


def test_dense_corrected_rerun_discards_stale_generated_artifacts() -> None:
    config = {
        "inputs": {"pdf_to_images": {"output_dir": None}},
        "detection": {
            "route": "dense",
            "precomputed_probe_candidates_root": "logs/old-run/candidates",
            "cnn_bands_from": "logs/old-run/bands",
            "probe_use_original_images": True,
            "resolved_route": {
                "profile": DENSE_ROUTE_PROFILE,
                "artifacts": {"probe_rescue_root": "logs/old-run/candidates"},
            },
        },
    }

    normalize_runtime_detection_config(config)

    detection = config["detection"]
    assert detection["route"] == "dense"
    assert "precomputed_probe_candidates_root" not in detection
    assert "cnn_bands_from" not in detection
    assert "probe_use_original_images" not in detection
    assert "resolved_route" not in detection
    assert config["inputs"]["pdf_to_images"]["output_dir"] == "auto"


def test_historical_precomputed_config_is_not_reinterpreted_as_dense() -> None:
    config = {
        "detection": {
            "precomputed_probe_candidates_root": "logs/reproduction/candidates",
            "cnn_bands_from": "logs/reproduction/bands",
        }
    }

    normalize_runtime_detection_config(config)

    route, selection = resolve_detector_route(config["detection"])
    assert route == "precomputed"
    assert selection == "legacy_precomputed_config"
    assert config["detection"]["precomputed_probe_candidates_root"].endswith("/candidates")


def test_production_entrypoint_reconstructs_dense_route_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "images" / "page_001.png"
    image.parent.mkdir()
    image.write_bytes(b"not-read-by-test")
    hybrid_root = tmp_path / "hybrid"
    probe_root = tmp_path / "probe"
    filtered_root = tmp_path / "dense" / "filtered"
    rescue_root = tmp_path / "dense" / "rescue"
    config = {"detection": {"cnn_model_path": "model.pth"}}

    from src.pipeline.detection import default_route
    from src.pipeline.detection.orchestrator import DetectorOrchestrator

    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_hybrid_detection",
        lambda self: {"hybrid_output_dir": hybrid_root, "commands": [["hybrid"]]},
    )
    monkeypatch.setattr(
        default_route,
        "reconstruct_current_run_dense_route",
        lambda **kwargs: DenseRouteArtifacts(
            image_paths=[image],
            filtered_root=filtered_root,
            probe_rescue_root=rescue_root,
            execution_summary={"image_count": 1},
        ),
    )
    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_probe_scan",
        lambda self: {"probe_output_dir": probe_root, "commands": [["probe"]]},
    )
    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_cnn_scoring",
        lambda self: {"commands": [["cnn"]]},
    )

    result = run_detection_step(
        config,
        [image],
        ["page_001"],
        "run",
        tmp_path / "run",
        dry_run=False,
    )

    detection = config["detection"]
    assert detection["route"] == "dense"
    assert detection["precomputed_probe_candidates_root"] == str(rescue_root)
    assert detection["cnn_bands_from"] == str(filtered_root)
    assert detection["probe_use_original_images"] is True
    assert detection["resolved_route"]["profile"] == DENSE_ROUTE_PROFILE
    assert detection["resolved_route"]["selection"] == "default"
    assert result["resolved_route"] == detection["resolved_route"]


def test_explicit_ordinary_route_skips_dense_reconstruction(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"not-read-by-test")
    config = {
        "detection": {
            "route": "ordinary",
            "enable_sr": False,
            "cnn_model_path": "model.pth",
        }
    }

    from src.pipeline.detection import default_route
    from src.pipeline.detection.orchestrator import DetectorOrchestrator

    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_hybrid_detection",
        lambda self: {"hybrid_output_dir": tmp_path / "hybrid", "commands": []},
    )

    def fail_reconstruction(**kwargs):
        raise AssertionError("ordinary route must not reconstruct dense candidates")

    monkeypatch.setattr(default_route, "reconstruct_current_run_dense_route", fail_reconstruction)
    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_probe_scan",
        lambda self: {"probe_output_dir": tmp_path / "probe", "commands": []},
    )
    monkeypatch.setattr(
        DetectorOrchestrator,
        "_run_cnn_scoring",
        lambda self: {"commands": []},
    )

    run_detection_step(
        config,
        [image],
        ["page_001"],
        "run",
        tmp_path / "run",
        dry_run=False,
    )

    assert config["detection"]["route"] == "ordinary"
    assert config["detection"]["enable_sr"] is False
    assert config["detection"]["resolved_route"]["profile"] == "legacy_ordinary"
