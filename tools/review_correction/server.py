#!/usr/bin/env python3
"""Package-scoped user review server. GT/developer routes live in gt_relabel_gui."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
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
from tools.review_correction.application import CorrectionApplication
from tools.review_correction.state import CorrectionState


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class ReviewPackage:
    """The handoff fixes every readable artifact and writable correction sink."""

    def __init__(self, handoff: Path):
        handoff = handoff.resolve()
        if handoff.name != "manual_correction_input.json":
            raise ValueError("Expected a package-local manual_correction_input.json")
        self.root = handoff.parent
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
        self.state = CorrectionState(self.root, self.pages, handoff)

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
            path = self.output(page, kind)
            _atomic_write(path, _payload(kind, merged))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            try:
                self.state.note_record_error(page, kind, str(exc))
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

    def _file(self, path: Path, *, json_type: bool = False) -> None:
        data = path.read_bytes()
        content_type = (
            "application/json"
            if json_type
            else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._trusted_host():
            return
        parsed = urlparse(self.path)
        package = self.server.package
        assets = {
            "/": "index.html",
            "/app.js": "app.js",
            "/app_manual.js": "app.js",
            "/strings.js": "strings.js",
            "/correction_state.js": "correction_state.js",
        }
        if parsed.path in assets:
            self._file(UI_ROOT / assets[parsed.path])
            return
        if parsed.path == "/api/result":
            try:
                self._file(self.server.application.result())
            except (ValueError, OSError, KeyError) as exc:
                self.send_error(400, str(exc))
            return
        if parsed.path == "/api/pages":
            self._json({"pages": package.pages})
            return
        if parsed.path == "/api/state":
            try:
                self._json(package.state.snapshot())
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self.send_error(400, str(exc))
            return
        if parsed.path == "/api/manual_corrections":
            query = parse_qs(parsed.query)
            kind = query.get("type", [None])[0]
            page = query.get("page", [None])[0]
            try:
                path = package.output(page, kind)
                self._json(_payload(kind, _load_items(path, kind)))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self.send_error(400, str(exc))
            return
        if parsed.path in {"/file", "/api/template", "/api/boxes"}:
            rel = parse_qs(parsed.query).get("path", [None])[0]
            allowed_fields = {
                "/file": {"image", "review_overlay"},
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
                if parsed.path == "/api/boxes":
                    self._json({"boxes": _load_boxes(path)})
                else:
                    self._file(path, json_type=parsed.path == "/api/template")
            except (ValueError, OSError) as exc:
                self.send_error(403, str(exc))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {
            "/api/save",
            "/api/export_movement_boundaries",
            "/api/state/pending",
            "/api/state/pending/clear",
            "/api/apply",
        }:
            self.send_error(404, "Not found")
            return
        if not self._trusted_write():
            return
        package = self.server.package
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 10_000_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object")
            if parsed.path == "/api/apply":
                if payload:
                    raise ValueError(
                        "Apply uses the active review package and accepts no paths or options"
                    )
                self._json(self.server.application.start())
                return
            if self.server.application.lock.locked():
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
            resolved = build_resolved_movement_boundaries(
                evidence=json.loads(evidence_bytes.decode("utf-8")),
                review=json.loads(review.read_text(encoding="utf-8")),
                evidence_artifact=evidence_rel,
                evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
            )
            _atomic_write(output, resolved)
            package.state.note_record_success(config["page"], "movement_boundary")
            self._json(
                {
                    "output": str(output),
                    "count": len(resolved.get("boundaries", [])),
                    "schema_version": resolved.get("schema_version"),
                }
            )
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            if parsed.path == "/api/export_movement_boundaries" and "config" in locals():
                try:
                    package.state.note_record_error(config["page"], "movement_boundary", str(exc))
                except (KeyError, ValueError):
                    pass
            self.send_error(400, str(exc))


def create_server(handoff: Path, *, port: int = 8010) -> HTTPServer:
    package = ReviewPackage(handoff)
    server = HTTPServer(("127.0.0.1", port), ReviewHandler)
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
