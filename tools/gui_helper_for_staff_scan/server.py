#!/usr/bin/env python3
"""Staff scan inspection GUI server (no external deps)."""

from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class PageItem:
    name: str
    page_dir: Path
    debug_json: Path
    crop_dir: Path
    row_band_debug: Path | None
    debug_image: Path | None


def safe_path(root: Path, rel: str) -> Path:
    candidate = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Path outside root.")
    return candidate


def scan_pages(root: Path) -> list[PageItem]:
    items: list[PageItem] = []
    per_page = root / "per_page"
    if not per_page.exists():
        return items
    for page_dir in sorted(per_page.glob("page_*")):
        if not page_dir.is_dir():
            continue
        debug_json = page_dir / "endbar_debug.json"
        crop_dir = page_dir / "endbar_debug_crops"
        if not debug_json.exists() or not crop_dir.exists():
            continue
        row_band_debug = page_dir / "row_band_debug.png"
        debug_image = page_dir / "endbar_debug.png"
        items.append(
            PageItem(
                name=page_dir.name,
                page_dir=page_dir,
                debug_json=debug_json,
                crop_dir=crop_dir,
                row_band_debug=row_band_debug if row_band_debug.exists() else None,
                debug_image=debug_image if debug_image.exists() else None,
            )
        )
    return items


def list_crops(crop_dir: Path) -> list[str]:
    crops = sorted(p.name for p in crop_dir.glob("*.png"))
    return crops


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(self.server.ui_root / "index.html")
            return
        if parsed.path == "/app.js":
            self._serve_file(self.server.ui_root / "app.js")
            return
        if parsed.path == "/api/pages":
            items = scan_pages(self.server.root)
            payload = []
            for item in items:
                payload.append(
                    {
                        "name": item.name,
                        "debug_json": str(item.debug_json.relative_to(self.server.root)),
                        "crop_dir": str(item.crop_dir.relative_to(self.server.root)),
                        "row_band_debug": str(item.row_band_debug.relative_to(self.server.root))
                        if item.row_band_debug
                        else None,
                        "debug_image": str(item.debug_image.relative_to(self.server.root))
                        if item.debug_image
                        else None,
                    }
                )
            self._serve_json(
                {
                    "pages": payload,
                    "root": str(self.server.root),
                    "per_page": str((self.server.root / "per_page").resolve()),
                    "page_count": len(payload),
                }
            )
            return
        if parsed.path == "/api/debug":
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [None])[0]
            if not rel:
                self.send_error(400, "Missing path")
                return
            try:
                path = safe_path(self.server.root, rel)
            except ValueError:
                self.send_error(403, "Invalid path")
                return
            if not path.exists():
                self.send_error(404, "Not found")
                return
            self._serve_file(path, force_json=True)
            return
        if parsed.path == "/api/crops":
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [None])[0]
            if not rel:
                self.send_error(400, "Missing path")
                return
            try:
                path = safe_path(self.server.root, rel)
            except ValueError:
                self.send_error(403, "Invalid path")
                return
            if not path.exists():
                self.send_error(404, "Not found")
                return
            crops = list_crops(path)
            payload = [str((path / name).relative_to(self.server.root)) for name in crops]
            self._serve_json({"crops": payload})
            return
        if parsed.path == "/file":
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [None])[0]
            if not rel:
                self.send_error(400, "Missing path")
                return
            try:
                path = safe_path(self.server.root, rel)
            except ValueError:
                self.send_error(403, "Invalid path")
                return
            self._serve_file(path)
            return
        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/save_scan":
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self.send_error(400, "Empty body")
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            page = payload.get("page")
            if not page:
                self.send_error(400, "Missing page")
                return
            scan_dir = self.server.root / "scan_logs"
            scan_dir.mkdir(parents=True, exist_ok=True)
            path = scan_dir / f"scan_log_{page}.json"
            existing = []
            if path.exists():
                try:
                    existing = json.loads(path.read_text()).get("scan_log", [])
                except Exception:
                    existing = []
            existing.append(payload)
            existing.sort(key=lambda item: (item.get("y", 0), item.get("band_height", 0)))
            path.write_text(json.dumps({"scan_log": existing}, indent=2))
            self._serve_json(
                {"status": "ok", "path": str(path), "count": len(existing), "items": existing}
            )
            return
        self.send_error(404, "Not found")

    def log_message(self, format, *args):
        return

    def _serve_json(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path, force_json: bool = False):
        if not path.exists():
            self.send_error(404, "Not found")
            return
        data = path.read_bytes()
        content_type = "application/json" if force_json else mimetypes.guess_type(path.name)[0]
        if not content_type:
            content_type = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Staff scan inspector GUI server.")
    parser.add_argument("--root", type=str, required=True, help="Path to a run dir with per_page/.")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5010)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    server = HTTPServer((args.host, args.port), Handler)
    server.root = root
    server.ui_root = Path(__file__).parent.resolve()
    print(f"Staff scan GUI: http://{args.host}:{args.port}")
    print(f"Run root: {root}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
