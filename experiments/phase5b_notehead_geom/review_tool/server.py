#!/usr/bin/env python3
"""
Minimal review tool server (no external deps).
Serves static UI and saves labels to JSON.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]


def safe_path(root: Path, rel: str) -> Path:
    candidate = (REPO_ROOT / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    if REPO_ROOT not in candidate.parents and candidate != REPO_ROOT:
        raise ValueError("Path outside repo root.")
    return candidate


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(self.server.ui_root / "index.html")
            return
        if parsed.path == "/app.js":
            self._serve_file(self.server.ui_root / "app.js")
            return
        if parsed.path == "/labels":
            self._serve_json(self.server.labels_config)
            return
        if parsed.path == "/manifest":
            self._serve_json(self.server.manifest)
            return
        if parsed.path == "/file":
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [None])[0]
            if not rel:
                self.send_error(400, "Missing path")
                return
            try:
                path = safe_path(REPO_ROOT, rel)
            except ValueError:
                self.send_error(403, "Invalid path")
                return
            self._serve_file(path)
            return
        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/save":
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8"))
            page = payload.get("page")
            labels = payload.get("labels", {})
            if not page:
                self.send_error(400, "Missing page")
                return
            out_path = self.server.label_root / f"{page}_labels.json"
            out_path.write_text(json.dumps(labels, indent=2))
            self._serve_json({"path": str(out_path)})
            return
        if parsed.path == "/summary":
            summary = {}
            for label_file in self.server.label_root.glob("*_labels.json"):
                page = label_file.stem.replace("_labels", "")
                data = json.loads(label_file.read_text())
                counts = {}
                for label in data.values():
                    counts[label] = counts.get(label, 0) + 1
                summary[page] = counts
            summary_md = ["# Label Summary", ""]
            for page, counts in summary.items():
                summary_md.append(f"## {page}")
                for label, count in sorted(counts.items()):
                    summary_md.append(f"- {label}: {count}")
                summary_md.append("")
            summary_path = self.server.label_root / "summary.md"
            summary_path.write_text("\n".join(summary_md))
            self._serve_json({"path": str(summary_path)})
            return
        self.send_error(404, "Not found")

    def _serve_json(self, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path):
        if not path.exists():
            self.send_error(404, "File not found")
            return
        ctype, _ = mimetypes.guess_type(str(path))
        ctype = ctype or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--label-root", type=Path, required=True)
    parser.add_argument("--labels-config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args()

    args.label_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.data_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.ui_root = Path(__file__).resolve().parent
    server.label_root = args.label_root
    server.manifest = json.loads(manifest_path.read_text())
    server.labels_config = json.loads(args.labels_config.read_text())

    print(f"Review tool running: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
