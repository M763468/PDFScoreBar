"""Versioned production model artifact manifests and local materialization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen

SCHEMA_VERSION = "pdfscorebar.model_artifact.v1"
MODEL_CACHE_ENV = "PDFSCOREBAR_MODEL_CACHE"
DEFAULT_CACHE_DIR = ".model_cache"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ModelArtifactError(RuntimeError):
    """Base class for model artifact contract failures."""


class ModelArtifactManifestError(ModelArtifactError):
    """Raised when a tracked manifest is invalid."""


class ModelArtifactMissingError(ModelArtifactError):
    """Raised when a required materialized artifact is missing."""


class ModelArtifactIntegrityError(ModelArtifactError):
    """Raised when an artifact digest does not match its manifest."""


@dataclass(frozen=True)
class ModelArtifactManifest:
    """Validated identity and materialization fields for one model artifact."""

    path: Path
    model_id: str
    version: str
    architecture: str
    asset_name: str
    sha256: str
    cache_path: Path
    repository: str | None
    release_tag: str | None
    ownership: str
    runtime_path: str | None
    raw: Mapping[str, Any]

    @property
    def is_downloadable(self) -> bool:
        return self.repository is not None and self.release_tag is not None

    @property
    def download_url(self) -> str:
        if not self.is_downloadable:
            raise ModelArtifactManifestError(
                f"Artifact {self.model_id}@{self.version} is operator-supplied; "
                "use the import command instead of materialize"
            )
        assert self.repository is not None
        assert self.release_tag is not None
        repository = self.repository.strip("/")
        if repository.count("/") != 1:
            raise ModelArtifactManifestError(
                f"Invalid release repository in {self.path}: {self.repository!r}"
            )
        return (
            f"https://github.com/{repository}/releases/download/"
            f"{quote(self.release_tag, safe='')}/{quote(self.asset_name, safe='')}"
        )


def _require_text(data: Mapping[str, Any], key: str, *, manifest_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} requires non-empty string field {key!r}"
        )
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _validate_relative_cache_path(value: str, *, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} has unsafe cache_path: {value!r}"
        )
    return path


def load_model_artifact_manifest(path: Path | str) -> ModelArtifactManifest:
    """Load and validate the immutable identity fields of a model artifact manifest."""
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelArtifactManifestError(
            f"Model artifact manifest not found: {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ModelArtifactManifestError(
            f"Invalid JSON in model artifact manifest {manifest_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ModelArtifactManifestError(
            f"Model artifact manifest must contain a JSON object: {manifest_path}"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ModelArtifactManifestError(
            f"Unsupported model artifact manifest schema in {manifest_path}: "
            f"{payload.get('schema_version')!r}; expected {SCHEMA_VERSION!r}"
        )

    release = payload.get("release")
    distribution = payload.get("distribution")
    if release is not None and not isinstance(release, dict):
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} field 'release' must be an object"
        )
    if distribution is not None and not isinstance(distribution, dict):
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} field 'distribution' must be an object"
        )
    if release is None and distribution is None:
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} requires 'release' or 'distribution'"
        )

    repository: str | None = None
    release_tag: str | None = None
    if isinstance(release, dict):
        repository = _require_text(release, "repository", manifest_path=manifest_path)
        release_tag = _require_text(release, "tag", manifest_path=manifest_path)
        asset_name = _require_text(release, "asset", manifest_path=manifest_path)
    else:
        assert isinstance(distribution, dict)
        mode = _require_text(distribution, "mode", manifest_path=manifest_path)
        if mode != "operator-supplied":
            raise ModelArtifactManifestError(
                f"Manifest {manifest_path} has unsupported distribution mode: {mode!r}"
            )
        asset_name = _require_text(distribution, "asset", manifest_path=manifest_path)

    digest = _require_text(payload, "sha256", manifest_path=manifest_path).lower()
    if not _SHA256_RE.fullmatch(digest):
        raise ModelArtifactManifestError(
            f"Manifest {manifest_path} has invalid sha256: {digest!r}"
        )

    cache_path_text = _require_text(payload, "cache_path", manifest_path=manifest_path)
    ownership = _optional_text(payload, "ownership") or (
        "repository-release" if release is not None else "external/operator-supplied"
    )

    return ModelArtifactManifest(
        path=manifest_path,
        model_id=_require_text(payload, "model_id", manifest_path=manifest_path),
        version=_require_text(payload, "version", manifest_path=manifest_path),
        architecture=_require_text(payload, "architecture", manifest_path=manifest_path),
        asset_name=asset_name,
        sha256=digest,
        cache_path=_validate_relative_cache_path(cache_path_text, manifest_path=manifest_path),
        repository=repository,
        release_tag=release_tag,
        ownership=ownership,
        runtime_path=_optional_text(payload, "runtime_path"),
        raw=payload,
    )


def get_model_cache_root(
    *, project_root: Path, cache_root: Path | str | None = None
) -> Path:
    """Resolve the local model cache root without touching experiment logs."""
    if cache_root is not None:
        return Path(cache_root)
    env_value = os.environ.get(MODEL_CACHE_ENV)
    if env_value:
        return Path(env_value)
    return project_root / DEFAULT_CACHE_DIR


def model_artifact_path(
    manifest: ModelArtifactManifest,
    *,
    project_root: Path,
    cache_root: Path | str | None = None,
) -> Path:
    root = get_model_cache_root(project_root=project_root, cache_root=cache_root)
    return root / manifest.cache_path


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(path: Path | str, *, expected_sha256: str) -> Path:
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise ModelArtifactMissingError(f"Model artifact is missing: {artifact_path}")
    actual = sha256_file(artifact_path)
    if actual != expected_sha256.lower():
        raise ModelArtifactIntegrityError(
            f"Model artifact SHA-256 mismatch: {artifact_path}; "
            f"expected={expected_sha256.lower()} actual={actual}"
        )
    return artifact_path


def verify_model_artifact_for_manifest(
    manifest_path: Path | str, artifact_path: Path | str
) -> Path:
    """Verify arbitrary bytes against the selected version in a tracked manifest."""
    manifest = load_model_artifact_manifest(manifest_path)
    return verify_model_artifact(artifact_path, expected_sha256=manifest.sha256)


def resolve_model_artifact(
    manifest_path: Path | str,
    *,
    project_root: Path,
    cache_root: Path | str | None = None,
) -> Path:
    """Resolve a cached production artifact and verify its digest before use."""
    manifest = load_model_artifact_manifest(manifest_path)
    artifact = model_artifact_path(
        manifest, project_root=project_root, cache_root=cache_root
    )
    try:
        return verify_model_artifact(artifact, expected_sha256=manifest.sha256)
    except ModelArtifactMissingError as exc:
        action = "materialize" if manifest.is_downloadable else "import"
        source_hint = "" if manifest.is_downloadable else " /path/to/model"
        raise ModelArtifactMissingError(
            f"{exc}. Materialize it explicitly with: python -m src.common.model_artifacts "
            f"{action} {manifest.path}{source_hint}"
        ) from exc


DownloadOpener = Callable[[Request], BinaryIO]


def _download_request(url: str) -> Request:
    headers = {"User-Agent": "PDFScoreBar-model-materializer"}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return Request(url, headers=headers)


def _publish_verified_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    force: bool,
) -> Path:
    verify_model_artifact(source, expected_sha256=expected_sha256)
    if destination.exists() and not force:
        return verify_model_artifact(destination, expected_sha256=expected_sha256)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
        shutil.copyfile(source, temp_path)
        verify_model_artifact(temp_path, expected_sha256=expected_sha256)
        os.replace(temp_path, destination)
        temp_path = None
        return destination
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def import_model_artifact(
    manifest_path: Path | str,
    source_path: Path | str,
    *,
    project_root: Path,
    cache_root: Path | str | None = None,
    force: bool = False,
) -> Path:
    """Verify operator-supplied bytes and atomically register them in the common cache."""
    manifest = load_model_artifact_manifest(manifest_path)
    artifact = model_artifact_path(
        manifest, project_root=project_root, cache_root=cache_root
    )
    return _publish_verified_file(
        Path(source_path).expanduser(),
        artifact,
        expected_sha256=manifest.sha256,
        force=force,
    )


def materialize_model_artifact(
    manifest_path: Path | str,
    *,
    project_root: Path,
    cache_root: Path | str | None = None,
    force: bool = False,
    opener: DownloadOpener = urlopen,
) -> Path:
    """Download one release asset atomically and verify it before publishing to cache."""
    manifest = load_model_artifact_manifest(manifest_path)
    if not manifest.is_downloadable:
        raise ModelArtifactError(
            f"Artifact {manifest.model_id}@{manifest.version} is operator-supplied; "
            f"use: python -m src.common.model_artifacts import {manifest.path} /path/to/{manifest.asset_name}"
        )
    artifact = model_artifact_path(
        manifest, project_root=project_root, cache_root=cache_root
    )
    if artifact.exists() and not force:
        return verify_model_artifact(artifact, expected_sha256=manifest.sha256)

    artifact.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{artifact.name}.",
            suffix=".tmp",
            dir=artifact.parent,
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
            with opener(_download_request(manifest.download_url)) as response:
                shutil.copyfileobj(response, temp_handle)
        verify_model_artifact(temp_path, expected_sha256=manifest.sha256)
        os.replace(temp_path, artifact)
        temp_path = None
        return artifact
    except ModelArtifactError:
        raise
    except Exception as exc:
        raise ModelArtifactError(
            f"Failed to materialize model artifact {manifest.model_id}@{manifest.version} "
            f"from {manifest.download_url}: {exc}"
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _find_project_root(manifest_path: Path) -> Path:
    manifest = manifest_path.resolve()
    for parent in (manifest.parent, *manifest.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "src").is_dir():
            return parent
    raise ModelArtifactError(
        f"Could not locate repository root above model manifest: {manifest_path}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("materialize", "verify", "path"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("manifest", type=Path)
        subparser.add_argument("--cache-root", type=Path)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("manifest", type=Path)
    import_parser.add_argument("source", type=Path)
    import_parser.add_argument("--cache-root", type=Path)
    verify_file_parser = subparsers.add_parser("verify-file")
    verify_file_parser.add_argument("manifest", type=Path)
    verify_file_parser.add_argument("source", type=Path)
    subparsers.choices["materialize"].add_argument("--force", action="store_true")
    import_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest_path = args.manifest
    project_root = _find_project_root(manifest_path)
    if args.command == "materialize":
        path = materialize_model_artifact(
            manifest_path,
            project_root=project_root,
            cache_root=args.cache_root,
            force=args.force,
        )
    elif args.command == "import":
        path = import_model_artifact(
            manifest_path,
            args.source,
            project_root=project_root,
            cache_root=args.cache_root,
            force=args.force,
        )
    elif args.command == "verify-file":
        path = verify_model_artifact_for_manifest(manifest_path, args.source)
    elif args.command == "verify":
        path = resolve_model_artifact(
            manifest_path,
            project_root=project_root,
            cache_root=args.cache_root,
        )
    else:
        manifest = load_model_artifact_manifest(manifest_path)
        path = model_artifact_path(
            manifest, project_root=project_root, cache_root=args.cache_root
        )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
