import hashlib
import json
from pathlib import Path

import pytest
import yaml

import src.pipeline.detection.restored_orchestrator as restored
from src.common.model_artifacts import (
    ModelArtifactIntegrityError,
    ModelArtifactMissingError,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = ROOT / "models/barline_cnn/manifest.json"
PRODUCTION_MANIFEST_CONFIG_PATH = "models/barline_cnn/manifest.json"
EXPECTED_SHA256 = "f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd"
EXPECTED_SIZE_BYTES = 16339553
EXPECTED_THRESHOLD = 0.4965248107910156
EXPECTED_RELEASE_TAG = "model-barline-cnn-issue296-d27-v1"
EXPECTED_RELEASE_ASSET = "cnn_classifier_epoch_9.pth"
EXPECTED_CACHE_PATH = "barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth"


def _write_test_manifest(tmp_path: Path, *, payload: bytes) -> Path:
    manifest = tmp_path / "models/barline_cnn/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "pdfscorebar.model_artifact.v1",
                "model_id": "barline-cnn",
                "version": "issue296-d27-v1",
                "architecture": "efficientnet_b0",
                "release": {
                    "repository": "M763468/PDFScoreBar",
                    "tag": EXPECTED_RELEASE_TAG,
                    "asset": EXPECTED_RELEASE_ASSET,
                },
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "cache_path": EXPECTED_CACHE_PATH,
                "production_contract": {
                    "cnn_threshold": EXPECTED_THRESHOLD,
                    "cnn_apply_nms": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_production_manifest_records_exact_published_d27_identity() -> None:
    payload = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "pdfscorebar.model_artifact.v1"
    assert payload["model_id"] == "barline-cnn"
    assert payload["version"] == "issue296-d27-v1"
    assert payload["architecture"] == "efficientnet_b0"
    assert payload["release"] == {
        "repository": "M763468/PDFScoreBar",
        "tag": EXPECTED_RELEASE_TAG,
        "asset": EXPECTED_RELEASE_ASSET,
    }
    assert payload["sha256"] == EXPECTED_SHA256
    assert payload["size_bytes"] == EXPECTED_SIZE_BYTES
    assert payload["cache_path"] == EXPECTED_CACHE_PATH
    assert payload["provenance"] == {
        "accepted_issue": 296,
        "accepted_pr": 310,
        "accepted_merge_commit": "49a9da6a5f352e48cffd79306d75acdc8da3d9e7",
        "accepted_experiment": "D27 current-producer candidate-aligned EfficientNet-B0",
        "source_checkpoint": (
            "logs/cnn_barline_classification/"
            "issue296_efficientnet_b0_current_candidate_aligned_v1/"
            "cnn_classifier_epoch_9.pth"
        ),
        "publication_issue": 315,
    }
    assert payload["production_contract"] == {
        "cnn_threshold": EXPECTED_THRESHOLD,
        "cnn_apply_nms": False,
        "training_evaluation_matcher": {
            "name": "center_anchor",
            "vov_threshold": 0.5,
            "xdist_threshold": 12.0,
        },
    }


def test_production_config_uses_manifest_without_logs_checkpoint_path() -> None:
    config = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text(encoding="utf-8"))
    detection = config["detection"]

    assert detection["cnn_model_manifest"] == PRODUCTION_MANIFEST_CONFIG_PATH
    assert detection.get("cnn_model_path") is None
    assert detection["cnn_threshold"] == EXPECTED_THRESHOLD
    assert detection["cnn_apply_nms"] is False


def test_verified_stage_e_resolves_matching_cached_artifact(tmp_path: Path, monkeypatch) -> None:
    payload = b"verified-stage-e-checkpoint"
    manifest = _write_test_manifest(tmp_path, payload=payload)
    cached = tmp_path / ".model_cache" / EXPECTED_CACHE_PATH
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)
    validated = []

    monkeypatch.setattr(restored, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        restored,
        "_validate_verified_cnn_checkpoint",
        lambda path: validated.append(path),
    )

    resolved = restored._resolve_verified_cnn_artifact(
        manifest,
        cnn_threshold=EXPECTED_THRESHOLD,
    )

    assert resolved == cached
    assert validated == [cached]


def test_verified_stage_e_fails_loud_on_cached_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    payload = b"verified-stage-e-checkpoint"
    manifest = _write_test_manifest(tmp_path, payload=payload)
    cached = tmp_path / ".model_cache" / EXPECTED_CACHE_PATH
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"corrupt")

    monkeypatch.setattr(restored, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        restored,
        "_validate_verified_cnn_checkpoint",
        lambda _path: pytest.fail("checkpoint validation must not run after digest failure"),
    )

    with pytest.raises(ModelArtifactIntegrityError, match="SHA-256 mismatch"):
        restored._resolve_verified_cnn_artifact(
            manifest,
            cnn_threshold=EXPECTED_THRESHOLD,
        )


def test_verified_stage_e_fails_loud_when_cached_artifact_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    payload = b"verified-stage-e-checkpoint"
    manifest = _write_test_manifest(tmp_path, payload=payload)

    monkeypatch.setattr(restored, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        restored,
        "_validate_verified_cnn_checkpoint",
        lambda _path: pytest.fail("checkpoint validation must not run for a missing artifact"),
    )

    with pytest.raises(ModelArtifactMissingError, match="Materialize it explicitly"):
        restored._resolve_verified_cnn_artifact(
            manifest,
            cnn_threshold=EXPECTED_THRESHOLD,
        )


def test_verified_stage_e_rejects_legacy_path_and_manifest_ambiguity(tmp_path: Path) -> None:
    config = {
        "detection": {
            "homr_profile": "stage_e_verified",
            "detector_route": "dense_full_pipeline",
            "cnn_model_manifest": PRODUCTION_MANIFEST_CONFIG_PATH,
            "cnn_model_path": "logs/legacy/model.pth",
            "cnn_threshold": EXPECTED_THRESHOLD,
            "cnn_apply_nms": False,
        }
    }
    orchestrator = restored.DetectorOrchestrator(
        config=config,
        images=[tmp_path / "page_001.png"],
        run_id="test",
        run_dir=tmp_path / "run",
        dry_run=True,
    )

    with pytest.raises(ValueError, match="does not accept detection.cnn_model_path"):
        orchestrator._run_cnn_scoring()
