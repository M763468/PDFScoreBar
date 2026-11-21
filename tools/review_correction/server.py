#!/usr/bin/env python3
"""Package-scoped user review server. GT/developer routes live in gt_relabel_gui."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import logging
import mimetypes
import os
import re
import socket
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.review.manual_correction_handoff import (  # noqa: E402
    build_manual_gui_config,
    load_manual_correction_handoff,
)
from tools.review_correction.application import CorrectionApplication, preview_numbering
from tools.review_correction.history import (
    CheckpointStore,
    atomic_bytes,
    package_path,
    safe_http_error_message,
    safe_recorded_error,
)
from tools.review_correction.legacy import import_attempt, list_attempts
from tools.review_correction.resume import create_session
from tools.review_correction.state import CorrectionState

LOGGER = logging.getLogger(__name__)


class _ReviewHTTPError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


_POST_CLIENT_ERROR = {
    "/api/save": "Could not save correction",
    "/api/checkpoints": "Could not save checkpoint",
    "/api/legacy/import": "Could not import legacy attempt",
    "/api/resume": "Could not resume review session",
    "/api/export_movement_boundaries": "Could not export movement boundaries",
    "/api/state/pending": "Could not update review state",
    "/api/state/pending/clear": "Could not update review state",
    "/api/apply": "Could not start corrected PDF generation",
    "/api/preview_numbering": "Could not preview numbering",
}
_POST_STORAGE_ERROR = {
    "/api/save": "Could not save correction",
    "/api/checkpoints": "Could not save checkpoint",
    "/api/legacy/import": "Could not import legacy attempt",
    "/api/resume": "Could not resume review session",
    "/api/export_movement_boundaries": "Could not export movement boundaries",
    "/api/state/pending": "Could not update review state",
    "/api/state/pending/clear": "Could not update review state",
    "/api/apply": "Could not start corrected PDF generation",
    "/api/preview_numbering": "Could not preview numbering",
}


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class ReviewPackage:
    """The handoff fixes every readable artifact and writable correction sink."""

    def __init__(self, handoff: Path):
        handoff = handoff.resolve()
        if handoff.name != "manual_correction_input.json":
            raise ValueError("Expected a package-local manual_correction_input.json")
        self.root = handoff.parent
        self.handoff_path = handoff
        config = build_manual_gui_config(
            load_manual_correction_handoff(handoff),
            handoff_path=handoff,
            mode="issue229_smoke_strict",
            require_existing_artifacts=True,
        )
        self.pages = config["pages"]
        self.reads: dict[str, Path] = {}
        self.outputs: dict[tuple[str, str], str] = {}
        self.writes: dict[str, Path] = {}
        correction_root = self.root / "corrections"
        if correction_root.is_symlink():
            raise ValueError("Corrections directory must not be a symlink")
        for page in self.pages:
            for key in (
                "image",
                "display_image",
                "numbering",
                "mmr",
                "barlines",
                "review_overlay",
                "movement_boundary_evidence",
            ):
                rel = page.get(key)
                if rel:
                    self.reads[rel] = self._resolve(rel)
            for kind, rel in page["manual_outputs"].items():
                self._declare_output(rel, correction_root)
                for page_key in ("page", "name"):
                    self.outputs[(str(page[page_key]), kind)] = rel
            rel = page.get("movement_boundary_resolved_output")
            if rel:
                self._declare_output(rel, correction_root)

        if set(self.reads.values()) & set(self.writes.values()):
            raise ValueError("Correction outputs overlap review artifacts")
        payload = load_manual_correction_handoff(handoff)
        if payload.get("resume"):
            rel = payload["resume"]["input_pdf"]
            self.reads[rel] = package_path(self.root, rel)
            if payload["resume"].get("background_pdf"):
                rel = payload["resume"]["background_pdf"]
                self.reads[rel] = package_path(self.root, rel)
        self.state = CorrectionState(self.root, self.pages, handoff)
        self.history = CheckpointStore(self)

    def _resolve(self, rel: str) -> Path:
        if not isinstance(rel, str) or Path(rel).is_absolute():
            raise ValueError("Invalid package path")
        path = (self.root / rel).resolve()
        if not _inside(path, self.root):
            raise ValueError("Path outside review package")
        return path

    def _declare_output(self, rel: str, correction_root: Path) -> None:
        if not _inside(self.root / rel, correction_root) or (self.root / rel) == correction_root:
            raise ValueError("Correction output must be under review/corrections")
        path = self._resolve(rel)
        if not _inside(path, correction_root):
            raise ValueError("Correction output escapes review/corrections")
        self.writes[rel] = path

    def readable(self, rel: str) -> Path:
        if rel not in self.reads or self._resolve(rel) != self.reads[rel]:
            raise ValueError("Artifact is not declared by the handoff")
        if not self.reads[rel].is_file():
            raise ValueError("Declared artifact is unavailable")
        return self.reads[rel]

    def writable(self, rel: str) -> Path:
        if rel not in self.writes or self._resolve(rel) != self.writes[rel]:
            raise ValueError("Output is not declared by the handoff")
        return self.writes[rel]

    def output(self, page: object, kind: object) -> Path:
        rel = self.outputs.get((str(page), str(kind)))
        if rel is None:
            raise ValueError("Unknown page or correction type")
        return self.writable(rel)

    def record_correction(self, page: object, kind: object, items: object) -> dict:
        """Save and publish its immutable checkpoint in one serialized transition."""
        with self.history.transaction():
            previous = {
                rel: path.read_bytes() if path.is_file() else None
                for rel in self.writes
                for path in [self.writable(rel)]
            }
            pending = dict(self.state.pending)
            try:
                result = self._record_correction(page, kind, items)
                result["checkpoint_id"] = self.history.capture()
                return result
            except Exception as exc:
                for rel, data in previous.items():
                    path = self.writable(rel)
                    if data is not None:
                        atomic_bytes(path, data)
                    elif path.exists():
                        path.unlink()
                self.state.pending = pending
                try:
                    self.state.note_record_error(
                        page,
                        kind,
                        safe_recorded_error(
                            exc,
                            "Could not save correction",
                            forbidden_roots=(self.root, self.root.parent),
                        ),
                    )
                except ValueError:
                    pass
                raise

    def _record_correction(self, page: object, kind: object, items: object) -> dict:
        """Record any correction type through one package-bound atomic transition.

        Explicit Save and immediate movement confirmation are UI triggers for the
        same operation. Pending edits/errors clear only after replacement succeeds.
        """
        try:
            path = self.output(page, kind)
            if not isinstance(items, list):
                raise ValueError("Correction items must be a list")
            if not all(isinstance(item, dict) for item in items):
                raise ValueError("Correction items must be objects")
            existing = _load_items(path, kind)
            merged = [item for item in existing if str(item.get("page")) != str(page)] + items
            config = next(p for p in self.pages if str(p["page"]) == str(page))
            manual_movement = kind == "movement_boundary" and not config.get(
                "movement_boundary_evidence"
            )
            if manual_movement:
                from src.pipeline.review.movement_boundary_review import (
                    build_manual_movement_boundaries,
                )

                # Validate before replacing either artifact. The consumer also
                # checks their shared review digest if the second write fails.
                build_manual_movement_boundaries(
                    review=_payload(kind, merged), review_artifact="", review_sha256=""
                )
                if any(str(item.get("page")) != str(page) for item in items):
                    raise ValueError("Movement decisions must target the selected page")
                for item in merged:
                    target = next((p for p in self.pages if p["page"] == item["page"]), None)
                    if target is None:
                        raise ValueError("Unknown movement boundary page")
                    numbering = json.loads(self.readable(target["numbering"]).read_bytes())
                    page_data = (numbering.get("pages") or [numbering])[0]
                    systems = page_data.get("systems", [])
                    system_ids = {
                        system.get("index", system.get("system", index))
                        for index, system in enumerate(systems)
                    }
                    if item["system"] not in system_ids:
                        raise ValueError("Unknown movement boundary system")
            path = self.output(page, kind)
            _atomic_write(path, _payload(kind, merged))
            if manual_movement:
                resolved = build_manual_movement_boundaries(
                    review=_payload(kind, merged),
                    review_artifact=config["manual_outputs"]["movement_boundary"],
                    review_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                _atomic_write(self.writable(config["movement_boundary_resolved_output"]), resolved)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            try:
                self.state.note_record_error(
                    page,
                    kind,
                    safe_recorded_error(
                        exc,
                        "Could not save correction",
                        forbidden_roots=(self.root, self.root.parent),
                    ),
                )
            except ValueError:
                pass
            raise
        self.state.note_record_success(page, kind)
        return {
            "output": str(path),
            "correction_type": kind,
            "count": len(merged),
            "page_count": len(items),
        }


def _payload(kind: str, items: list) -> dict:
    return {"schema_version": 1, "correction_type": kind, "items": items}


def _atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_items(path: Path, kind: str) -> list:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("correction_type") != kind:
        raise ValueError("Existing correction type does not match")
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Existing correction items must be a list")
    return items


def _load_boxes(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("predictions") if isinstance(data, dict) and "predictions" in data else data
    boxes = []
    if isinstance(records, list):
        for record in records:
            if isinstance(record, list) and len(record) == 4:
                boxes.append({"bbox": [int(value) for value in record]})
            elif isinstance(record, dict):
                bbox = (
                    record.get("barline_location")
                    or record.get("orig_bbox")
                    or record.get("pred_bbox")
                )
                if bbox and len(bbox) == 4:
                    box = {"bbox": [int(value) for value in bbox]}
                    if record.get("barline_type") or record.get("type"):
                        box["barline_type"] = record.get("barline_type") or record.get("type")
                    boxes.append(box)
    return boxes


class ReviewHandler(BaseHTTPRequestHandler):
    def _trusted_host(self) -> bool:
        # A loopback bind alone does not stop browser requests sent through DNS rebinding.
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403, "Use the local review address")
            return False
        return True

    def _trusted_write(self) -> bool:
        if not self._trusted_host():
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://127.0.0.1:{self.server.server_port}":
            self.send_error(403, "Cross-origin writes are forbidden")
            return False
        # Cross-site forms and no-cors fetch can send text/plain but cannot send
        # application/json without a CORS preflight, which this server does not grant.
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_error(415, "JSON content type required")
            return False
        return True

    def _json(self, obj: object) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(
        self,
        path: Path,
        *,
        json_type: bool = False,
        download_filename: str | None = None,
    ) -> None:
        data = path.read_bytes()
        content_type = (
            "application/json"
            if json_type
            else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if download_filename:
            from urllib.parse import quote

            safe_ascii = "".join(
                ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\"} else "_"
                for ch in Path(download_filename).name
            )
            encoded_utf8 = quote(Path(download_filename).name, safe="")
            self.send_header(
                "Content-Disposition",
                f"inline; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded_utf8}",
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _review_context(self):
        return self.server

    def _context(self):
        context = self._review_context()
        ids = parse_qs(urlparse(self.path).query, keep_blank_values=True).get("session", [])
        if not ids:
            return context.package, context.application
        if len(ids) != 1 or not re.fullmatch(r"s_[0-9a-f]{32}", ids[0]):
            LOGGER.warning(
                "Rejected invalid review session parameter on %s",
                urlparse(self.path).path,
            )
            raise _ReviewHTTPError(400, "Invalid review session")
        session = ids[0]
        if session not in context.sessions:
            try:
                path = package_path(
                    context.package.root,
                    f"resumed_sessions/{session}/review/manual_correction_input.json",
                )
            except (ValueError, OSError):
                LOGGER.exception("Rejected unsafe review session path for %s", session)
                raise _ReviewHTTPError(404, "Review session not found") from None
            if not path.is_file():
                LOGGER.warning("Unknown review session requested: %s", session)
                raise _ReviewHTTPError(404, "Review session not found")
            try:
                package = ReviewPackage(path)
                application = CorrectionApplication(package, path)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                LOGGER.exception("Failed to open review session %s", session)
                raise _ReviewHTTPError(404, "Review session unavailable") from None
            context.sessions[session] = (package, application)
        return context.sessions[session]

    def do_GET(self) -> None:
        if not self._trusted_host():
            return
        parsed = urlparse(self.path)
        assets = {
            "/": "index.html",
            "/app.js": "app.js",
            "/history.js": "history.js",
            "/app_manual.js": "app.js",
            "/strings.js": "strings.js",
            "/correction_state.js": "correction_state.js",
        }
        if parsed.path in assets:
            try:
                self._file(UI_ROOT / assets[parsed.path])
            except FileNotFoundError:
                LOGGER.warning("Review interface asset missing for %s", parsed.path)
                self.send_error(404, "Not found")
            except OSError:
                LOGGER.exception("Could not read review interface asset for %s", parsed.path)
                self.send_error(500, "Could not load review interface")
            return
        try:
            package, application = self._context()
        except _ReviewHTTPError as exc:
            self.send_error(exc.status, exc.message)
            return
        if parsed.path == "/api/checkpoints":
            try:
                self._json(
                    {
                        "checkpoints": package.history.list(),
                        "applications": package.history.list_applications(),
                        "legacy_attempts": list_attempts(package),
                    }
                )
            except FileNotFoundError:
                LOGGER.exception("Review history file missing")
                self.send_error(404, "Review history is unavailable")
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                LOGGER.exception("Failed to load review history")
                self.send_error(500, "Review history is unavailable")
            return
        if parsed.path == "/api/result":
            try:
                result_path = application.result()
                self._file(result_path, download_filename=result_path.name)
            except FileNotFoundError:
                LOGGER.warning("Corrected final PDF file missing")
                self.send_error(404, "The corrected final PDF is unavailable")
            except ValueError as exc:
                message = str(exc)
                if message in {
                    "No corrected final PDF has been generated",
                    "The corrected final PDF is unavailable",
                }:
                    self.send_error(404, message)
                elif message in {
                    "The corrected final PDF changed after generation",
                    "The validated numbering sidecar changed",
                }:
                    LOGGER.warning("Corrected final PDF verification failed: %s", message)
                    self.send_error(409, message)
                else:
                    LOGGER.exception("Could not resolve corrected final PDF")
                    self.send_error(404, "The corrected final PDF is unavailable")
            except (OSError, KeyError):
                LOGGER.exception("Could not read corrected final PDF")
                self.send_error(500, "Could not read the corrected final PDF")
            return
        if parsed.path == "/api/pages":
            self._json({"pages": package.pages})
            return
        if parsed.path == "/api/state":
            try:
                self._json(package.state.snapshot())
            except FileNotFoundError:
                LOGGER.exception("Review state file missing")
                self.send_error(404, "Review state is unavailable")
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                LOGGER.exception("Failed to load review state")
                self.send_error(500, "Review state is unavailable")
            return
        if parsed.path == "/api/manual_corrections":
            query = parse_qs(parsed.query)
            kind = query.get("type", [None])[0]
            page = query.get("page", [None])[0]
            try:
                path = package.output(page, kind)
            except ValueError as exc:
                if str(exc) == "Unknown page or correction type":
                    self.send_error(400, "Unknown page or correction type")
                else:
                    LOGGER.warning("Rejected manual corrections output lookup")
                    self.send_error(403, "Correction output is not allowed")
                return
            except OSError:
                LOGGER.exception("Failed to resolve correction output path")
                self.send_error(500, "Could not load saved corrections")
                return
            try:
                self._json(_payload(kind, _load_items(path, kind)))
            except FileNotFoundError:
                LOGGER.warning("Saved correction file missing")
                self.send_error(404, "Saved corrections are unavailable")
            except OSError:
                LOGGER.exception("Could not read saved corrections")
                self.send_error(500, "Could not load saved corrections")
            except (ValueError, json.JSONDecodeError):
                LOGGER.exception("Saved corrections file is invalid")
                self.send_error(400, "Saved corrections are invalid")
            return
        if parsed.path in {"/file", "/api/template", "/api/boxes"}:
            rel = parse_qs(parsed.query).get("path", [None])[0]
            allowed_fields = {
                "/file": {"image", "display_image", "review_overlay"},
                "/api/template": {"numbering", "mmr", "movement_boundary_evidence"},
                "/api/boxes": {"barlines"},
            }
            if not any(
                page.get(field) == rel
                for page in package.pages
                for field in allowed_fields[parsed.path]
            ):
                self.send_error(403, "Artifact is not declared for this route")
                return
            try:
                path = package.readable(rel)
            except ValueError as exc:
                if str(exc) == "Declared artifact is unavailable":
                    LOGGER.warning("Declared artifact missing for %s", parsed.path)
                    self.send_error(404, "Declared artifact is unavailable")
                else:
                    LOGGER.warning("Rejected unsafe artifact access on %s", parsed.path)
                    self.send_error(403, "Artifact is not allowed")
                return
            except OSError:
                LOGGER.exception("Failed to resolve declared artifact on %s", parsed.path)
                self.send_error(500, "Could not read declared artifact")
                return
            try:
                if parsed.path == "/api/boxes":
                    self._json({"boxes": _load_boxes(path)})
                else:
                    self._file(path, json_type=parsed.path == "/api/template")
            except FileNotFoundError:
                LOGGER.warning("Declared artifact file disappeared on %s", parsed.path)
                self.send_error(404, "Declared artifact is unavailable")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                LOGGER.exception("Failed to serve declared artifact on %s", parsed.path)
                self.send_error(500, "Could not read declared artifact")
            return
        self.send_error(404, "Not found")

    def _record_movement_export_error(
        self,
        parsed_path: str,
        package: ReviewPackage | None,
        config: dict | None,
        message: str,
    ) -> None:
        if parsed_path != "/api/export_movement_boundaries" or package is None or config is None:
            return
        try:
            package.state.note_record_error(config["page"], "movement_boundary", message)
        except (KeyError, ValueError):
            pass

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in _POST_CLIENT_ERROR:
            self.send_error(404, "Not found")
            return
        if not self._trusted_write():
            return
        package: ReviewPackage | None = None
        config: dict | None = None
        try:
            package, application = self._context()
            raw_size = self.headers.get("Content-Length", "0")
            if not re.fullmatch(r"[0-9]{1,12}", raw_size):
                raise _ReviewHTTPError(400, "Invalid request size")
            size = int(raw_size)
            limit = 43_000_000 if parsed.path == "/api/resume" else 10_000_000
            if size < 0 or size > limit:
                raise _ReviewHTTPError(400, "Invalid request size")
            try:
                payload = json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise _ReviewHTTPError(400, "Invalid JSON request body") from None
            if not isinstance(payload, dict):
                raise _ReviewHTTPError(400, "Request body must be an object")
            if parsed.path in {"/api/checkpoints", "/api/legacy/import", "/api/resume"}:
                snap = package.state.snapshot()
                if snap["package"]["counts"]["pending"] or package.state.record_errors:
                    raise ValueError("Save or resolve current edits before history operations")
            if parsed.path == "/api/legacy/import":
                if set(payload) != {"attempt_id"}:
                    raise ValueError("Legacy import accepts only an attempt ID")
                with package.history.transaction():
                    checkpoint = import_attempt(package, payload["attempt_id"])
                self._json({"checkpoint_id": checkpoint})
                return
            if parsed.path == "/api/checkpoints":
                if set(payload) - {"label"}:
                    raise ValueError("Checkpoint accepts only a label")
                with package.history.transaction():
                    checkpoint = package.history.capture(label=payload.get("label", ""), force=True)
                self._json({"checkpoint_id": checkpoint})
                return
            if parsed.path == "/api/resume":
                if set(payload) != {"checkpoint_id", "pdf_base64"}:
                    raise ValueError("Resume requires a checkpoint ID and uploaded PDF")
                if not isinstance(payload.get("pdf_base64"), str):
                    raise _ReviewHTTPError(400, "Invalid base64 payload")
                try:
                    data = base64.b64decode(payload["pdf_base64"], validate=True)
                except (binascii.Error, ValueError):
                    raise _ReviewHTTPError(400, "Invalid base64 payload") from None
                with package.history.transaction():
                    session = create_session(
                        package,
                        payload["checkpoint_id"],
                        data,
                        session_root=self._review_context().package.root,
                        ownership_package=self._review_context().package,
                    )
                self._json({"session": session, "url": "/?session=" + session})
                return
            if parsed.path == "/api/apply":
                if payload:
                    raise ValueError(
                        "Apply uses the active review package and accepts no paths or options"
                    )
                self._json(application.start())
                return
            if parsed.path == "/api/preview_numbering":
                if payload:
                    raise ValueError(
                        "Numbering preview uses saved corrections and accepts no options"
                    )
                if application.lock.locked():
                    raise ValueError(
                        "Wait for corrected PDF generation before previewing numbering"
                    )
                self._json(preview_numbering(package.handoff_path))
                return
            if application.lock.locked():
                raise ValueError("Wait for corrected PDF generation before editing corrections")
            if parsed.path in {"/api/state/pending", "/api/state/pending/clear"}:
                page = payload.get("page")
                kind = payload.get("correction_type")
                if parsed.path.endswith("/clear"):
                    package.state.clear_pending(page, kind)
                else:
                    package.state.set_pending(page, kind, payload.get("items"))
                self._json(package.state.snapshot())
                return
            if parsed.path == "/api/save":
                self._json(
                    package.record_correction(
                        payload.get("page"), payload.get("correction_type"), payload.get("items")
                    )
                )
                return
            config = next((p for p in package.pages if p.get("movement_boundary_evidence")), None)
            if config is None:
                raise ValueError("No movement boundary evidence is attached")
            from src.pipeline.review.movement_boundary_review import (
                build_resolved_movement_boundaries,
            )

            evidence_rel = config["movement_boundary_evidence"]
            review_rel = config["manual_outputs"]["movement_boundary"]
            output_rel = config["movement_boundary_resolved_output"]
            evidence = package.readable(evidence_rel)
            review = package.writable(review_rel)
            output = package.writable(output_rel)
            if not review.is_file():
                raise ValueError("Save movement review decisions before export")
            evidence_bytes = evidence.read_bytes()
            review_bytes = review.read_bytes()
            resolved = build_resolved_movement_boundaries(
                evidence=json.loads(evidence_bytes.decode("utf-8")),
                review=json.loads(review_bytes),
                evidence_artifact=evidence_rel,
                evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
            )
            with package.history.transaction():
                if evidence.read_bytes() != evidence_bytes or review.read_bytes() != review_bytes:
                    raise ValueError("Movement inputs changed during finalization")
                output = package.writable(output_rel)
                previous = output.read_bytes() if output.exists() else None
                try:
                    _atomic_write(output, resolved)
                    checkpoint = package.history.capture()
                    package.state.note_record_success(config["page"], "movement_boundary")
                except Exception:
                    if previous is None:
                        output.unlink(missing_ok=True)
                    else:
                        atomic_bytes(output, previous)
                    raise
            self._json(
                {
                    "output": str(output),
                    "count": len(resolved.get("boundaries", [])),
                    "checkpoint_id": checkpoint,
                    "schema_version": resolved.get("schema_version"),
                }
            )
        except _ReviewHTTPError as exc:
            self.send_error(exc.status, exc.message)
        except FileNotFoundError:
            LOGGER.warning("Required review file missing during POST %s", parsed.path)
            self._record_movement_export_error(
                parsed.path, package, config, "Required review file is unavailable"
            )
            self.send_error(404, "Required review file is unavailable")
        except OSError as exc:
            LOGGER.exception("Storage error during POST %s", parsed.path)
            fallback = _POST_STORAGE_ERROR.get(parsed.path, "Could not complete review request")
            roots = (package.root, package.root.parent) if package is not None else ()
            self._record_movement_export_error(
                parsed.path,
                package,
                config,
                safe_recorded_error(exc, fallback, forbidden_roots=roots),
            )
            self.send_error(500, fallback)
        except (
            ValueError,
            KeyError,
            TypeError,
            binascii.Error,
            json.JSONDecodeError,
        ) as exc:
            if isinstance(exc, ValueError) and str(exc) == "Declared artifact is unavailable":
                LOGGER.warning("Declared artifact unavailable during POST %s", parsed.path)
                self._record_movement_export_error(
                    parsed.path, package, config, "Declared artifact is unavailable"
                )
                self.send_error(404, "Declared artifact is unavailable")
                return
            fallback = _POST_CLIENT_ERROR.get(parsed.path, "Could not complete review request")
            roots = (package.root, package.root.parent) if package is not None else ()
            message = safe_http_error_message(exc, fallback, forbidden_roots=roots)
            if message == fallback:
                LOGGER.exception("Rejected POST %s with sanitized error", parsed.path)
            else:
                LOGGER.warning("Rejected POST %s: %s", parsed.path, message)
            self._record_movement_export_error(parsed.path, package, config, message)
            self.send_error(400, message)


class _ExclusivePort:
    """Refuse a port that another server already listens on (#535).

    http.server enables SO_REUSEADDR. On Windows that lets a second server bind a port in
    use, so two review/browser servers answered the same address nondeterministically.
    Windows binds with SO_EXCLUSIVEADDRUSE instead; POSIX keeps SO_REUSEADDR, which
    never allows two listeners there.
    """

    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class LocalHTTPServer(_ExclusivePort, HTTPServer):
    pass


class LocalThreadingHTTPServer(_ExclusivePort, ThreadingHTTPServer):
    pass


def create_server(handoff: Path, *, port: int = 8010) -> HTTPServer:
    package = ReviewPackage(handoff)
    server = LocalHTTPServer(("127.0.0.1", port), ReviewHandler)
    server.sessions = {}
    server.package = package
    server.application = CorrectionApplication(package, handoff)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="User review of one correction package")
    parser.add_argument(
        "--handoff", type=Path, required=True, help="review/manual_correction_input.json"
    )
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    try:
        server = create_server(args.handoff, port=args.port)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Correction review: http://127.0.0.1:{server.server_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
