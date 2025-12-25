#!/usr/bin/env python3
"""Minimal GT relabel GUI server (no external deps)."""
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
class Item:
    page: str
    gt_index: int
    dir_path: Path
    image_path: Path
    template_path: Path


def safe_path(root: Path, rel: str) -> Path:
    candidate = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Path outside root.")
    return candidate


def scan_items(root: Path) -> list[Item]:
    items: list[Item] = []
    for page_dir in sorted(root.glob("page_*")):
        if not page_dir.is_dir():
            continue
        for fn_dir in sorted(page_dir.glob("fn_*")):
            if not fn_dir.is_dir():
                continue
            image_path = fn_dir / "crop_x4.png"
            template_path = fn_dir / "edit_template.json"
            if not image_path.exists() or not template_path.exists():
                continue
            try:
                gt_index = int(fn_dir.name.replace("fn_", ""))
            except ValueError:
                continue
            items.append(
                Item(
                    page=page_dir.name,
                    gt_index=gt_index,
                    dir_path=fn_dir,
                    image_path=image_path,
                    template_path=template_path,
                )
            )
    return items


def item_payload(item: Item, root: Path) -> dict:
    return {
        "page": item.page,
        "gt_index": item.gt_index,
        "dir": str(item.dir_path.relative_to(root)),
        "image": str(item.image_path.relative_to(root)),
        "template": str(item.template_path.relative_to(root)),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(self.server.ui_root / "index.html")
            return
        if parsed.path == "/app.js":
            self._serve_file(self.server.ui_root / "app.js")
            return
        if parsed.path == "/api/items":
            items = scan_items(self.server.root)
            payload = [item_payload(item, self.server.root) for item in items]
            self._serve_json({"items": payload})
            return
        if parsed.path == "/api/template":
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
            self._serve_file(path, force_json=True)
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
        if parsed.path != "/api/save":
            self.send_error(404, "Not found")
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body.decode("utf-8"))
        rel = payload.get("path")
        if not rel:
            self.send_error(400, "Missing path")
            return
        try:
            path = safe_path(self.server.root, rel)
        except ValueError:
            self.send_error(403, "Invalid path")
            return
        if not path.exists():
            self.send_error(404, "Template not found")
            return
        data = json.loads(path.read_text())
        status = payload.get("status")
        edited_bbox = payload.get("edited_bbox")
        if status:
            data["status"] = status
        if edited_bbox is not None:
            data["edited_bbox"] = [int(v) for v in edited_bbox]
        path.write_text(json.dumps(data, indent=2))
        self._serve_json({"path": str(path), "status": data.get("status")})

    def _serve_json(self, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path, force_json: bool = False):
        if not path.exists():
            self.send_error(404, "File not found")
            return
        if force_json:
            ctype = "application/json"
        else:
            ctype, _ = mimetypes.guess_type(str(path))
            ctype = ctype or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    server.ui_root = Path(__file__).resolve().parent
    server.root = args.root.resolve()

    print(f"GT relabel GUI running: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
