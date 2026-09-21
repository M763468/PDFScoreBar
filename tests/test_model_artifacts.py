import hashlib
import io
import json

import pytest

from src.common.model_artifacts import (
    ModelArtifactIntegrityError,
    ModelArtifactManifestError,
    ModelArtifactMissingError,
    get_model_cache_root,
    load_model_artifact_manifest,
    materialize_model_artifact,
    resolve_model_artifact,
)


@pytest.fixture(autouse=True)
def _isolate_model_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSCOREBAR_MODEL_CACHE", str(tmp_path / ".model_cache"))


def _write_manifest(
    tmp_path, *, payload=b"accepted-d27-checkpoint", cache_path="cnn/d27/model.pth"
):
    manifest = tmp_path / "models" / "barline_cnn" / "manifest.json"
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
                    "tag": "model-barline-cnn-issue296-d27-v1",
                    "asset": "cnn_classifier_epoch_9.pth",
                },
                "sha256": hashlib.sha256(payload).hexdigest(),
                "cache_path": cache_path,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_default_model_cache_uses_xdg_cache_home(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFSCOREBAR_MODEL_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    assert get_model_cache_root(project_root=tmp_path / "checkout") == (
        tmp_path / "xdg" / "pdfscorebar" / "models"
    )


def test_default_model_cache_uses_user_cache_when_xdg_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFSCOREBAR_MODEL_CACHE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert get_model_cache_root(project_root=tmp_path / "checkout") == (
        tmp_path / "home" / ".cache" / "pdfscorebar" / "models"
    )


def test_explicit_model_cache_env_overrides_xdg_default(tmp_path, monkeypatch):
    override = tmp_path / "explicit"
    monkeypatch.setenv("PDFSCOREBAR_MODEL_CACHE", str(override))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    assert get_model_cache_root(project_root=tmp_path / "checkout") == override


def test_default_shared_cache_is_reused_across_worktrees(tmp_path, monkeypatch):
    payload = b"accepted-d27-checkpoint"
    worktree_a = tmp_path / "worktree-a"
    worktree_b = tmp_path / "worktree-b"
    manifest_a = _write_manifest(worktree_a, payload=payload)
    manifest_b = _write_manifest(worktree_b, payload=payload)

    monkeypatch.delenv("PDFSCOREBAR_MODEL_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    cached = tmp_path / "xdg" / "pdfscorebar" / "models" / "cnn" / "d27" / "model.pth"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    assert resolve_model_artifact(manifest_a, project_root=worktree_a) == cached
    assert resolve_model_artifact(manifest_b, project_root=worktree_b) == cached


def test_resolve_model_artifact_accepts_matching_cached_bytes(tmp_path):
    payload = b"accepted-d27-checkpoint"
    manifest_path = _write_manifest(tmp_path, payload=payload)
    cached = tmp_path / ".model_cache" / "cnn" / "d27" / "model.pth"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    assert resolve_model_artifact(manifest_path, project_root=tmp_path) == cached


def test_resolve_model_artifact_fails_loud_when_missing(tmp_path):
    manifest_path = _write_manifest(tmp_path)

    with pytest.raises(ModelArtifactMissingError, match="Materialize it explicitly"):
        resolve_model_artifact(manifest_path, project_root=tmp_path)


def test_resolve_model_artifact_fails_loud_on_digest_mismatch(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    cached = tmp_path / ".model_cache" / "cnn" / "d27" / "model.pth"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"corrupt")

    with pytest.raises(ModelArtifactIntegrityError, match="SHA-256 mismatch"):
        resolve_model_artifact(manifest_path, project_root=tmp_path)


def test_materialize_model_artifact_populates_empty_cache_and_verifies_digest(tmp_path):
    payload = b"accepted-d27-checkpoint"
    manifest_path = _write_manifest(tmp_path, payload=payload)
    seen_urls = []

    def opener(request):
        seen_urls.append(request.full_url)
        return io.BytesIO(payload)

    cached = materialize_model_artifact(
        manifest_path,
        project_root=tmp_path,
        opener=opener,
    )

    assert cached.read_bytes() == payload
    assert seen_urls == [
        "https://github.com/M763468/PDFScoreBar/releases/download/"
        "model-barline-cnn-issue296-d27-v1/cnn_classifier_epoch_9.pth"
    ]
    assert resolve_model_artifact(manifest_path, project_root=tmp_path) == cached


def test_materialize_model_artifact_does_not_replace_cache_with_bad_download(tmp_path):
    payload = b"accepted-d27-checkpoint"
    manifest_path = _write_manifest(tmp_path, payload=payload)

    def opener(_request):
        return io.BytesIO(b"wrong-checkpoint")

    with pytest.raises(ModelArtifactIntegrityError, match="SHA-256 mismatch"):
        materialize_model_artifact(
            manifest_path,
            project_root=tmp_path,
            opener=opener,
        )

    cached = tmp_path / ".model_cache" / "cnn" / "d27" / "model.pth"
    assert not cached.exists()


def test_materialize_model_artifact_refuses_corrupt_existing_cache_without_force(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    cached = tmp_path / ".model_cache" / "cnn" / "d27" / "model.pth"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"corrupt")

    with pytest.raises(ModelArtifactIntegrityError, match="SHA-256 mismatch"):
        materialize_model_artifact(manifest_path, project_root=tmp_path)


def test_manifest_rejects_unsafe_cache_path(tmp_path):
    manifest_path = _write_manifest(tmp_path, cache_path="../outside/model.pth")

    with pytest.raises(ModelArtifactManifestError, match="unsafe cache_path"):
        load_model_artifact_manifest(manifest_path)


def test_manifest_rejects_invalid_sha256(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["sha256"] = "not-a-digest"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ModelArtifactManifestError, match="invalid sha256"):
        load_model_artifact_manifest(manifest_path)
