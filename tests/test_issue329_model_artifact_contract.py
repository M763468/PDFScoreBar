from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.common.model_artifacts import (
    ModelArtifactIntegrityError,
    import_model_artifact,
    resolve_model_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OMR_MANIFEST = PROJECT_ROOT / "models" / "omr_dln" / "manifest.json"


@pytest.fixture(autouse=True)
def isolated_model_cache(tmp_path: Path, monkeypatch) -> None:
    # Fixture imports must never publish synthetic bytes into the user's shared cache.
    monkeypatch.setenv("PDFSCOREBAR_MODEL_CACHE", str(tmp_path / ".model_cache"))


def _write_external_manifest(tmp_path: Path, *, version: str, payload: bytes) -> Path:
    manifest = tmp_path / "models" / "fixture" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "pdfscorebar.model_artifact.v1",
                "model_id": "fixture-model",
                "version": version,
                "architecture": "fixture",
                "distribution": {
                    "mode": "operator-supplied",
                    "asset": "model.bin",
                },
                "sha256": hashlib.sha256(payload).hexdigest(),
                "cache_path": f"fixture-model/{version}/model.bin",
                "ownership": "external/operator-supplied",
                "runtime_path": f"/opt/pdfscore-external/fixture-model/{version}/model.bin",
                "provenance": {"fixture_version": version},
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_version_and_digest_update_registers_new_selected_bytes(tmp_path: Path) -> None:
    v1 = b"model-v1"
    manifest = _write_external_manifest(tmp_path, version="v1", payload=v1)
    source = tmp_path / "source.bin"
    source.write_bytes(v1)

    v1_cached = import_model_artifact(manifest, source, project_root=tmp_path)
    assert v1_cached == tmp_path / ".model_cache/fixture-model/v1/model.bin"
    assert resolve_model_artifact(manifest, project_root=tmp_path) == v1_cached

    v2 = b"model-v2"
    manifest = _write_external_manifest(tmp_path, version="v2", payload=v2)
    source.write_bytes(v2)
    v2_cached = import_model_artifact(manifest, source, project_root=tmp_path)

    assert v2_cached == tmp_path / ".model_cache/fixture-model/v2/model.bin"
    assert v2_cached.read_bytes() == v2
    assert v1_cached.read_bytes() == v1


def test_silent_byte_replacement_under_same_version_fails_integrity(tmp_path: Path) -> None:
    payload = b"selected-model"
    manifest = _write_external_manifest(tmp_path, version="v1", payload=payload)
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    cached = import_model_artifact(manifest, source, project_root=tmp_path)
    cached.write_bytes(b"silent-replacement")

    with pytest.raises(ModelArtifactIntegrityError, match="SHA-256 mismatch"):
        resolve_model_artifact(manifest, project_root=tmp_path)


def test_omr_dln_weight_is_no_longer_a_selected_artifact() -> None:
    # #522: hybrid support uses x4 HOMR; the unlicensed OMR-DLN weight is not selected.
    assert not OMR_MANIFEST.exists()


def test_canonical_docker_validation_uses_manifest_resolver_and_read_only_mount() -> None:
    script = (PROJECT_ROOT / "scripts" / "docker_runtime_validation.sh").read_text(encoding="utf-8")

    assert "models/omr_dln/manifest.json" not in script
    assert "OMR_DLN_MODEL_PATH" not in script
    assert "src.pipeline.detection.model_selection" in script
    assert "PDFSCOREBAR_MODEL_CACHE" in script


def test_docker_build_uses_first_party_sr_and_no_realesrgan_release() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    # Issue #533: the Real-ESRGAN release weights are neither downloaded nor shipped.
    assert "Real-ESRGAN/releases/download" not in dockerfile
    assert "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1" not in dockerfile
    assert "PDFSCORE_REALESRGAN_WEIGHTS_DIR" not in dockerfile
    assert "resolve_first_party_sr" in dockerfile


def test_inventory_documents_all_canonical_model_families() -> None:
    inventory = (PROJECT_ROOT / "docs" / "contracts" / "MODEL_ARTIFACT_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    for identity in (
        "barline-cnn",
        "pdfscorebar-sr-x4",
        "Maintained HOMR runtime assets",
        "Pinned Stage-E HOMR assets",
    ):
        assert identity in inventory
