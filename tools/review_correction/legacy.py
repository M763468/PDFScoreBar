"""Validate and import immutable pre-checkpoint apply inputs, never inferred success."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from src.pipeline.review.apply_corrections import _resolve_source_manifest_path
from tools.review_correction.history import digest, encoded, package_path

ATTEMPT = re.compile(r"attempt_[0-9]{4,}\Z")


def validate_attempt(package, name):
    from tools.review_correction.server import ReviewPackage
    from tools.review_correction.state import _digest

    if not isinstance(name, str) or not ATTEMPT.fullmatch(name):
        raise ValueError("Invalid legacy attempt ID")
    root = package_path(package.root, f"application_runs/{name}")
    consumed_path = package_path(root, "consumed_inputs.json")
    consumed = json.loads(consumed_path.read_text())
    if consumed.get("checkpoint_id"):
        raise ValueError("This application already has a checkpoint")
    if (
        _digest(
            {"source": consumed["source_identity"], "corrections": consumed["corrections_identity"]}
        )
        != consumed["identity"]
    ):
        raise ValueError("Legacy consumed identity is inconsistent")
    handoff = package_path(root, "input_review/manual_correction_input.json")
    if package_path(handoff.parent, "corrections/.correction_state.json").exists():
        raise ValueError("Legacy input must not contain application state")
    snapshot = ReviewPackage(handoff)
    if snapshot.pages != package.pages or set(snapshot.reads) != set(package.reads):
        raise ValueError("Legacy page selection does not match this review")
    for relative in snapshot.reads:
        if digest(snapshot.readable(relative).read_bytes()) != digest(
            package.readable(relative).read_bytes()
        ):
            raise ValueError("Legacy source artifacts changed")
    original_handoff = json.loads(package.handoff_path.read_text())
    saved_handoff = json.loads(handoff.read_text())
    original_body = {k: v for k, v in original_handoff.items() if k != "source_manifest"}
    saved_body = {k: v for k, v in saved_handoff.items() if k != "source_manifest"}
    if original_body != saved_body or saved_handoff.get("resume"):
        raise ValueError("Legacy handoff does not match the original review")
    manifest = _resolve_source_manifest_path(original_handoff, package.root)
    if not manifest.is_file():
        raise ValueError("Original retained manifest is unavailable")
    # The old adapter changed only source_manifest to its absolute runtime path.
    # Accept that relocation only for the retained job's exact suffix/name.
    declared = Path(saved_handoff.get("source_manifest", ""))
    if declared != manifest and declared.parts[-4:] != manifest.parts[-4:]:
        raise ValueError("Legacy retained manifest layout does not match")
    sources = {rel: digest(path.read_bytes()) for rel, path in snapshot.state.source_paths.items()}
    sources["manual_correction_input.json"] = digest(package.handoff_path.read_bytes())
    sources["source_manifest"] = digest(manifest.read_bytes())
    if _digest(sources) != consumed["source_identity"]:
        raise ValueError("Legacy source identity cannot be reproduced")
    if (
        snapshot.state.capture_identity()["corrections_identity"]
        != consumed["corrections_identity"]
    ):
        raise ValueError("Legacy corrections changed after application")
    return (
        snapshot,
        manifest,
        {
            "kind": "legacy_saved_inputs",
            "attempt_id": name,
            "consumed_inputs_sha256": digest(consumed_path.read_bytes()),
            "original_identity": {
                key: consumed[key]
                for key in ("identity", "source_identity", "corrections_identity")
            },
            "source_manifest_sha256": digest(manifest.read_bytes()),
            "original_snapshot_handoff_sha256": digest(handoff.read_bytes()),
        },
    )


def list_attempts(package):
    root = package_path(package.root, "application_runs")
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.iterdir()):
        if not ATTEMPT.fullmatch(path.name):
            continue
        consumed = package_path(package.root, f"application_runs/{path.name}/consumed_inputs.json")
        if not consumed.is_file():
            continue
        try:
            data = json.loads(consumed.read_text())
            if data.get("checkpoint_id"):
                continue
            validate_attempt(package, path.name)
            result.append({"id": path.name, "available": True, "status": "saved_inputs_only"})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result.append(
                {
                    "id": path.name,
                    "available": False,
                    "status": "unverified",
                    "error": str(exc)[:300],
                }
            )
    return result


def import_attempt(package, name):
    """Caller holds this package's history transaction. No legacy files are changed."""
    snapshot, manifest, origin = validate_attempt(package, name)
    for item in package.history.list():
        if package.history.get(item["id"]).get("origin") == origin:
            return item["id"]
    with tempfile.TemporaryDirectory(prefix=".legacy-", dir=package.history.root) as temporary:
        review = Path(temporary) / "review"
        review.mkdir()
        for rel in sorted(set(snapshot.reads) | set(snapshot.writes)):
            source = snapshot.readable(rel) if rel in snapshot.reads else snapshot.writable(rel)
            if source.is_file():
                target = package_path(review, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        payload = json.loads(snapshot.handoff_path.read_text())
        payload.pop("source_artifact_root", None)
        payload["source_manifest"] = str(manifest)
        (review / "manual_correction_input.json").write_bytes(encoded(payload))
        from tools.review_correction.server import ReviewPackage

        staged = ReviewPackage(review / "manual_correction_input.json")
        if (
            staged.state.capture_identity()["corrections_identity"]
            != origin["original_identity"]["corrections_identity"]
        ):
            raise ValueError("Legacy corrections changed during import")
        validate_attempt(package, name)
        return package.history.capture(
            label=f"Legacy {name}", force=True, snapshot=staged, origin=origin
        )
