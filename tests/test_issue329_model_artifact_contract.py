from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.common.model_artifacts import (
    ModelArtifactIntegrityError,
    import_model_artifact,
    load_model_artifact_manifest,
    resolve_model_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OMR_MANIFEST = PROJECT_ROOT / "models" / "omr_dln" / "manifest.json"


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


def test_omr_manifest_records_selected_version_identity_and_external_ownership() -> None:
    manifest = load_model_artifact_manifest(OMR_MANIFEST)

    assert manifest.model_id == "omr-dln-measures"
    assert manifest.version == "phase1-validated-v1"
    assert manifest.sha256 == (
        "00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212"
    )
    assert manifest.ownership == "external/operator-supplied"
    assert manifest.is_downloadable is False
    assert manifest.cache_path == Path(
        "omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"
    )
    assert manifest.runtime_path == (
        "/opt/pdfscore-external/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"
    )


def test_canonical_docker_validation_uses_manifest_resolver_and_read_only_mount() -> None:
    script = (PROJECT_ROOT / "scripts" / "docker_runtime_validation.sh").read_text(
        encoding="utf-8"
    )

    assert "models/omr_dln/manifest.json" in script
    assert "src.common.model_artifacts verify" in script
    assert "src.common.model_artifacts verify-file" in script
    assert '"$omr_host:$omr_container:ro"' in script
    assert "PDFSCOREBAR_MODEL_CACHE" in script
