"""Package-bound, immutable correction checkpoints with content-addressed files."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.review.apply_corrections import _resolve_source_manifest_path

CHECKPOINT_ID = re.compile(r"cp_[0-9a-f]{64}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def package_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Invalid package-relative path")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw == Path("."):
        raise ValueError("Artifact must be package-relative")
    path = root / raw
    for current in [path, *path.parents]:
        if current == root:
            break
        if current.is_symlink():
            raise ValueError("Package artifacts must not use symlinks")
    if root.resolve() not in path.resolve().parents:
        raise ValueError("Artifact escapes package")
    return path


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def relocate_manifest(data, manifest_path):
    """Only the retained engine-job layout permits a fixed-prefix relocation."""
    actual = manifest_path.parent.resolve()
    declared = Path(str(data.get("run_dir", "")))
    if len(actual.parts) < 4 or list(actual.parts[-3:-1]) != [".engine-retained", "runs"]:
        return deepcopy(data)
    if not declared.is_absolute() or declared.parts[-3:] != actual.parts[-3:]:
        raise ValueError("Retained source layout does not match its manifest")
    old_root, new_root = declared.parents[2], actual.parents[2]

    def convert(value):
        if isinstance(value, str) and (
            value == str(old_root) or value.startswith(str(old_root) + "/")
        ):
            target = new_root / value[len(str(old_root)) :].lstrip("/")
            if not target.resolve().is_relative_to(new_root):
                raise ValueError("Retained reference escaped job root")
            return str(target)
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value

    return convert(data)


class ReviewBusyError(ValueError):
    """A live operation owns the package transaction or application lock."""


class CheckpointStore:
    def __init__(self, package):
        self.package = package
        self.root = package.root / "history"

    def _prepare(self):
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError("History must remain inside the review package")
        self.root.mkdir(exist_ok=True)
        for name in ("blobs", "checkpoints", "applications"):
            path = self.root / name
            if path.is_symlink():
                raise ValueError("History directories must not use symlinks")
            path.mkdir(exist_ok=True)

    @contextmanager
    def transaction(self, *, allow_apply=False):
        self._prepare()
        fd = os.open(self.root / ".transaction.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReviewBusyError("Another review operation is in progress") from exc
            if not allow_apply:
                apply_lock = package_path(self.package.root, "application_runs/.apply.lock")
                if apply_lock.exists() or apply_lock.is_symlink():
                    afd = os.open(apply_lock, os.O_RDWR | os.O_NOFOLLOW)
                    with os.fdopen(afd, "r+") as active:
                        try:
                            fcntl.flock(active, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError as exc:
                            raise ReviewBusyError(
                                "Wait for corrected PDF generation before saving"
                            ) from exc
            yield

    def put(self, data):
        key = digest(data)
        target = self.root / "blobs" / key
        if target.is_symlink():
            raise ValueError("History blob is a symlink")
        if not target.exists():
            fd, name = tempfile.mkstemp(prefix=".blob-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(name, target)
                except FileExistsError:
                    pass
            finally:
                os.unlink(name)
        if digest(target.read_bytes()) != key:
            raise ValueError("Immutable history blob changed")
        return {"sha256": key, "size": len(data)}

    def blob(self, ref):
        key = ref.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Invalid history blob identity")
        path = self.root / "blobs" / key
        if path.is_symlink():
            raise ValueError("History blob is a symlink")
        data = path.read_bytes()
        if len(data) != ref["size"] or digest(data) != key:
            raise ValueError("History blob changed or is incomplete")
        return data

    def _source_context(self):
        payload = json.loads(self.package.handoff_path.read_text())
        path = _resolve_source_manifest_path(payload, self.package.root)
        if not path.is_file():
            return None
        raw = path.read_bytes()
        manifest = relocate_manifest(json.loads(raw), path)
        context = {
            "original_manifest": self.put(raw),
            "manifest": manifest,
            "bases": {},
            "dependencies": {},
            "config_inputs": {},
        }
        # The base geometry must not silently fall back to an already-corrected
        # final layout when a checkpoint is resumed into another package.
        for page in payload["pages"]:
            base = path.parent / "intermediate" / page["page_id"] / "numbering_base.json"
            if base.is_file():
                context["bases"][page["page_id"]] = self.put(base.read_bytes())
        documents = []
        for page in manifest.get("pages", []):
            reference = page.get("source_reference", {})
            document = reference.get("source_document", {})
            if document.get("path"):
                documents.append(
                    (document["path"], document.get("sha256"), reference.get("source_page"))
                )
        if (
            documents
            and len({(p, h) for p, h, _ in documents}) == 1
            and all(isinstance(i, int) and i >= 0 for _, _, i in documents)
        ):
            source = Path(documents[0][0])
            data = source.read_bytes()
            if digest(data) != documents[0][1]:
                raise ValueError("Original PDF no longer matches retained provenance")
            context["source_pdf"] = self.put(data)
            context["source_pages"] = [i for _, _, i in documents]
        for name in ("measure_overrides", "barline_overrides", "movement_boundaries"):
            value = manifest.get("config", {}).get("inputs", {}).get(name)
            if isinstance(value, str):
                source = Path(value)
                if not source.is_absolute():
                    source = path.parent / source
                if source.is_file():
                    context["config_inputs"][name] = self.put(source.read_bytes())

        def dependencies(value):
            if isinstance(value, dict):
                for item in value.values():
                    dependencies(item)
            elif isinstance(value, list):
                for item in value:
                    dependencies(item)
            elif isinstance(value, str):
                item = Path(value)
                # Retained page references, not model discovery or arbitrary
                # traversal of the surrounding host filesystem.
                if (
                    item.is_absolute()
                    and item.is_file()
                    and item.suffix.lower() in {".json", ".png", ".jpg", ".tif", ".npy"}
                ):
                    context["dependencies"][str(item)] = digest(item.read_bytes())

        dependencies(manifest.get("pages", []))
        return context

    def capture(self, *, label="", force=False):
        """Caller holds transaction. Publish one immutable manifest last."""
        self._prepare()
        if not isinstance(label, str) or len(label) > 100:
            raise ValueError("Checkpoint label must be at most 100 characters")
        identity = self.package.state.capture_identity()
        if not force:
            for item in reversed(self.list()):
                if item["identity"] == identity:
                    self.validate_dependencies(item["id"])
                    return item["id"]
        refs = {}
        for rel in sorted(set(self.package.reads) | set(self.package.writes)):
            path = (
                self.package.readable(rel)
                if rel in self.package.reads
                else self.package.writable(rel)
            )
            refs[rel] = self.put(path.read_bytes()) if path.is_file() else None
        refs["manual_correction_input.json"] = self.put(self.package.handoff_path.read_bytes())
        value = {
            "schema_version": 1,
            "created_at": now(),
            "label": label,
            "identity": identity,
            "files": refs,
            "source_context": self._source_context(),
        }
        if self.package.state.capture_identity() != identity:
            raise ValueError("Review changed while saving checkpoint")
        data = encoded(value)
        checkpoint = "cp_" + digest(data)
        directory = self.root / "checkpoints" / checkpoint
        directory.mkdir()
        try:
            atomic_bytes(directory / "checkpoint.json", data)
        except BaseException:
            shutil.rmtree(directory)
            raise
        return checkpoint

    def get(self, checkpoint):
        self._prepare()
        if not isinstance(checkpoint, str) or not CHECKPOINT_ID.fullmatch(checkpoint):
            raise ValueError("Invalid checkpoint ID")
        directory = self.root / "checkpoints" / checkpoint
        path = directory / "checkpoint.json"
        if directory.is_symlink() or path.is_symlink():
            raise ValueError("Checkpoint must not use symlinks")
        value = json.loads(path.read_text())
        if value.get("schema_version") != 1 or "cp_" + digest(encoded(value)) != checkpoint:
            raise ValueError("Checkpoint metadata changed")
        for rel, ref in value["files"].items():
            package_path(self.package.root, rel)
            if ref is not None:
                self.blob(ref)
        return value

    def list(self):
        self._prepare()
        result = []
        for directory in (self.root / "checkpoints").iterdir():
            if (
                not CHECKPOINT_ID.fullmatch(directory.name)
                or not (directory / "checkpoint.json").is_file()
            ):
                continue
            value = self.get(directory.name)
            result.append(
                {
                    "id": directory.name,
                    "created_at": value["created_at"],
                    "label": value["label"],
                    "identity": value["identity"],
                    "can_resume_pdf": bool(value.get("source_context", {}).get("source_pdf"))
                    if value.get("source_context")
                    else False,
                }
            )
        return sorted(result, key=lambda item: item["created_at"])

    def validate_dependencies(self, checkpoint):
        value = self.get(checkpoint)
        context = value.get("source_context") or {}
        for path, expected in context.get("dependencies", {}).items():
            source = Path(path)
            if not source.is_file() or digest(source.read_bytes()) != expected:
                raise ValueError("Retained source dependency changed or is unavailable")
        return value

    def materialize(self, checkpoint, review):
        value = self.validate_dependencies(checkpoint)
        review.mkdir(parents=True, exist_ok=False)
        for rel, ref in value["files"].items():
            if ref is not None:
                path = package_path(review, rel)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.blob(ref))
        context = value.get("source_context")
        if context:
            retained = review.parent / "retained"
            retained.mkdir()
            manifest = deepcopy(context["manifest"])
            for page_id, ref in context["bases"].items():
                path = package_path(retained, f"intermediate/{page_id}/numbering_base.json")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.blob(ref))
            for name, ref in context.get("config_inputs", {}).items():
                path = retained / "imports" / f"{name}.json"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(self.blob(ref))
                manifest["config"]["inputs"][name] = f"imports/{name}.json"
            if context.get("source_pdf"):
                (retained / "source.pdf").write_bytes(self.blob(context["source_pdf"]))
            (retained / "manifest.json").write_bytes(encoded(manifest))
            handoff = json.loads((review / "manual_correction_input.json").read_text())
            handoff.pop("source_artifact_root", None)
            handoff["source_manifest"] = "../retained/manifest.json"
            (review / "manual_correction_input.json").write_bytes(encoded(handoff))
        return value

    def application_record(self, attempt, value=None):
        self._prepare()
        if not re.fullmatch(r"attempt_[0-9]{4,}", attempt):
            raise ValueError("Invalid application ID")
        path = self.root / "applications" / f"{attempt}.json"
        if path.is_symlink():
            raise ValueError("Application record must not be a symlink")
        if value is not None:
            atomic_bytes(path, encoded({"schema_version": 1, **value}))
        result = json.loads(path.read_text())
        if not isinstance(result, dict) or result.get("schema_version") != 1:
            raise ValueError("Invalid application history record")
        return result

    def list_applications(self):
        """Retain every failure; recover abandoned runs only under the save lock."""
        self._prepare()
        names = sorted(path.stem for path in (self.root / "applications").glob("attempt_*.json"))
        records = {name: self.application_record(name) for name in names}
        if any(record.get("status") == "running" for record in records.values()):
            try:
                with self.transaction():
                    package = self.package.state.snapshot()["package"]
                    last = package["last_successful_result"] or {}
                    for name in names:
                        record = self.application_record(name)
                        if record.get("status") != "running":
                            continue
                        attested = (
                            (package.get("last_application") or {}).get("status") == "succeeded"
                            and last.get("identity") == record.get("identity", {}).get("identity")
                            and Path(last.get("corrected_run") or "").parent
                            == self.package.root / "application_runs" / name
                        )
                        updated = {
                            **record,
                            "status": "succeeded" if attested else "interrupted",
                            "finished_at": now(),
                        }
                        if attested:
                            updated["result"] = last
                        else:
                            updated["error"] = "Application ended without an attested success"
                        records[name] = self.application_record(name, updated)
            except ReviewBusyError:
                # A live apply owns the lock; its running record remains running.
                pass
        return [{"id": name, **records[name]} for name in names]
