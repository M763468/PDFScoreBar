"""User-facing correction state derived from package and result content identities."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATE_FILENAME = ".correction_state.json"
CORRECTION_TYPES = (
    "mmr_measure_span",
    "measure_construction",
    "barline_construction",
    "movement_boundary",
)
LABELS = {
    "none": "No unrecorded edit",
    "none": "No unrecorded edit",
    "pending": "Edit not recorded",
    "not_recorded": "No correction recorded",
    "recorded": "Correction recorded",
    "not_applied": "No corrected result yet",
    "current": "Corrected result is current",
    "stale": "Recorded corrections changed since this result",
    "applying": "Generating corrected result",
    "error": "Needs attention",
    "mixed": "Review has different correction states",
    "package_mixed": "Review has different correction states",
}


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _file_identity(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CorrectionState:
    """Track page/type edits and successful result provenance for one review package."""

    def __init__(self, root: Path, pages: list[dict], handoff_path: Path):
        self.root = root.resolve()
        self.pages = pages
        self.handoff_path = handoff_path.resolve()
        self.source_paths = {
            rel: (self.root / rel).resolve()
            for page in pages
            for field in ("image", "numbering", "mmr", "barlines", "movement_boundary_evidence")
            if (rel := page.get(field))
        }
        self.pending: dict[tuple[str, str], str] = {}
        self.record_errors: dict[tuple[str, str], str] = {}
        self.apply_error: str | None = None
        self.applying = False
        self.metadata_path = self.root / "corrections" / STATE_FILENAME
        if (self.root / "corrections").is_symlink():
            raise ValueError("Corrections directory must not be a symlink")
        if self.metadata_path.is_symlink():
            raise ValueError("Correction state metadata must not be a symlink")
        self._metadata = self._read_metadata()

    def _read_metadata(self) -> dict:
        path = self.metadata_path
        if not path.exists():
            return {"schema_version": SCHEMA_VERSION, "last_successful_result": None}
        if path.is_symlink() or not path.is_file():
            raise ValueError("Correction state metadata is not a regular file")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Correction state metadata is invalid") from exc
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported correction state metadata")
        if not isinstance(data.get("last_successful_result"), (dict, type(None))):
            raise ValueError("Invalid last successful result metadata")
        return data

    def _safe_write_metadata(self) -> None:
        path = self.metadata_path
        directory = path.parent
        if directory.is_symlink():
            raise ValueError("Corrections directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("Correction state metadata must not be a symlink")
        fd, temporary = tempfile.mkstemp(prefix=".correction_state.", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._metadata, stream, indent=2, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _paths_for(self, page: dict, kind: str) -> list[Path]:
        rels = []
        rel = page.get("manual_outputs", {}).get(kind)
        if rel:
            rels.append(rel)
        if kind == "movement_boundary" and page.get("movement_boundary_resolved_output"):
            rels.append(page["movement_boundary_resolved_output"])
        corrections_root = self.root / "corrections"
        if corrections_root.is_symlink():
            raise ValueError("Corrections directory must not be a symlink")
        paths = []
        for rel in rels:
            raw_path = self.root / rel
            path = raw_path.resolve()
            if raw_path.is_symlink() or path == corrections_root or corrections_root.resolve() not in path.parents:
                raise ValueError("Correction output escapes review/corrections")
            paths.append(path)
        return paths

    def _path_for(self, page: dict, kind: str) -> Path | None:
        paths = self._paths_for(page, kind)
        return paths[0] if paths else None

    def _content_items(self, path: Path | None, kind: str) -> tuple[bool, list]:
        if path is None or not path.exists():
            return False, []
        if path.is_symlink() or not path.is_file():
            raise ValueError("Correction file is not a regular file")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("correction_type") != kind:
            raise ValueError("Existing correction type does not match")
        items = value.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Existing correction items must be a list")
        return True, items

    def _source_identity(self, rel: str) -> str | None:
        path = self.root / rel
        if path.resolve() != self.source_paths[rel] or self.root not in path.resolve().parents:
            raise ValueError("Declared source artifact changed its package path")
        return _file_identity(path)

    def capture_identity(self) -> dict:
        source_files: dict[str, str | None] = {}
        for page in self.pages:
            for field in (
                "image", "numbering", "mmr", "barlines", "movement_boundary_evidence"
            ):
                rel = page.get(field)
                if rel:
                    source_files[rel] = self._source_identity(rel)
        if self.handoff_path.is_symlink():
            raise ValueError("Review handoff must not be a symlink")
        source_files[self.handoff_path.name] = _file_identity(self.handoff_path)
        try:
            handoff_data = json.loads(self.handoff_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            handoff_data = {}
        from src.pipeline.review.apply_corrections import _resolve_source_manifest_path

        manifest_path = _resolve_source_manifest_path(handoff_data, self.root)
        if manifest_path.is_file():
            source_files["source_manifest"] = _file_identity(manifest_path)
        correction_files: dict[str, Any] = {}
        for page in self.pages:
            page_id = str(page.get("page", page.get("name", page.get("page_id", ""))))
            for kind in CORRECTION_TYPES:
                paths = self._paths_for(page, kind)
                if not paths:
                    continue
                correction_files[f"{page_id}:{kind}"] = {
                    "files": [
                        {"exists": path.exists(), "content": _digest(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else None}
                        for path in paths
                    ],
                }
        source = _digest(source_files)
        corrections = _digest(correction_files)
        return {
            "source_identity": source,
            "corrections_identity": corrections,
            "identity": _digest({"source": source, "corrections": corrections}),
        }

    def set_pending(self, page: object, kind: object, items: list) -> None:
        key = self._key(page, kind)
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError("Correction items must be objects")
        self.pending[key] = _digest(items)

    def clear_pending(self, page: object, kind: object) -> None:
        self.pending.pop(self._key(page, kind), None)

    def _key(self, page: object, kind: object) -> tuple[str, str]:
        key = (str(page), str(kind))
        if key[1] not in CORRECTION_TYPES or not any(
            self._path_for(config, key[1]) is not None
            and str(config.get("page", config.get("name", config.get("page_id", "")))) == key[0]
            for config in self.pages
        ):
            raise ValueError("Unknown page or correction type")
        return key

    def note_record_error(self, page: object, kind: object, error: str) -> None:
        self.record_errors[self._key(page, kind)] = str(error)[:500]

    def note_record_success(self, page: object, kind: object) -> None:
        key = self._key(page, kind)
        self.pending.pop(key, None)
        self.record_errors.pop(key, None)

    def begin_apply(self) -> dict:
        identity = self.capture_identity()
        snap = self.snapshot()
        if self.applying or self.record_errors or any(
            state["edit_status"] == "pending" for state in snap["states"]
        ):
            raise ValueError("Resolve pending edits or errors before generating a corrected result")
        self.applying = True
        self.apply_error = None
        return identity

    def finish_apply(
        self,
        identity: dict,
        *,
        corrected_run: str | None = None,
        final_pdf: str | None = None,
        final_pdf_sha256: str | None = None,
        result_identity: str | None = None,
    ) -> dict:
        current = self.capture_identity()
        if any(current.get(key) != identity.get(key) for key in ("source_identity", "corrections_identity")):
            self.fail_apply("Review inputs changed while corrected result was generated")
            raise ValueError(self.apply_error)
        result = {
            **identity,
            "result_identity": result_identity or _digest({
                "run": corrected_run,
                "final_pdf_sha256": final_pdf_sha256,
                "consumed": identity["identity"],
            }),
            "corrected_run": corrected_run,
            "final_pdf": final_pdf,
            "final_pdf_sha256": final_pdf_sha256,
        }
        previous = self._metadata.get("last_successful_result")
        self._metadata["last_successful_result"] = result
        try:
            self._safe_write_metadata()
        except Exception as exc:
            self._metadata["last_successful_result"] = previous
            self.fail_apply(f"Could not record corrected result identity: {exc}")
            raise
        self.applying = False
        self.apply_error = None
        return result

    def fail_apply(self, error: str) -> None:
        self.applying = False
        self.apply_error = str(error)[:500]

    def snapshot(self) -> dict:
        current = self.capture_identity()
        last = self._metadata.get("last_successful_result")
        matched = bool(last and last.get("identity") == current["identity"])
        states = []
        counts = {"pending": 0, "recorded": 0, "not_recorded": 0, "current": 0, "stale": 0, "not_applied": 0, "applying": 0, "error": 0}
        for page_config in self.pages:
            page_id = str(page_config.get("page", page_config.get("name", page_config.get("page_id", ""))))
            for kind in CORRECTION_TYPES:
                path = self._path_for(page_config, kind)
                if path is None:
                    continue
                paths = self._paths_for(page_config, kind)
                primary_exists, items = self._content_items(path, kind)
                exists = primary_exists or any(p.exists() for p in paths[1:])
                key = (page_id, kind)
                page_items = [item for item in items if str(item.get("page")) == page_id]
                pending = self.pending.get(key) is not None and self.pending[key] != _digest(page_items)
                record_error = self.record_errors.get(key)
                application = (
                    "applying" if self.applying else "error" if self.apply_error else
                    "current" if matched else "stale" if last else "not_applied"
                )
                state = {
                    "page": page_id,
                    "page_id": str(page_config.get("name", page_config.get("page_id", page_id))),
                    "correction_type": kind,
                    "edit_status": "pending" if pending else "none",
                    "recording_status": "recorded" if exists else "not_recorded",
                    "application_status": application,
                    "source_identity": current["source_identity"],
                    "recorded_identity": _digest(page_items) if exists else None,
                    "applied_identity": last.get("identity") if last else None,
                }
                if record_error or self.apply_error:
                    state["error"] = record_error or self.apply_error
                states.append(state)
                recording_status = "recorded" if page_items else "not_recorded"
                state["recording_status"] = recording_status
                counts["pending" if pending else recording_status] += 1
                counts[application] += 1
                if record_error or self.apply_error:
                    counts["error"] += 1
        statuses = {state["application_status"] for state in states}
        packages = {state["recording_status"] for state in states}
        package_status = (
            "error" if self.apply_error or self.record_errors else
            "mixed" if len(packages) > 1 or len(statuses) > 1 else
            "pending" if counts["pending"] else
            next(iter(statuses), "not_applied")
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "package": {
                "status": package_status,
                "counts": counts,
                "current_result": last if matched else None,
                "last_successful_result": last,
                "current_identity": current,
            },
            "states": states,
            "labels": LABELS,
        }
