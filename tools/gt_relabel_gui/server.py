#!/usr/bin/env python3
"""Minimal GT relabel GUI server (no external deps)."""
from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import time
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
Box = tuple[int, int, int, int]


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


def load_boxes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    records = data.get("predictions") if isinstance(data, dict) and "predictions" in data else data
    boxes: list[dict] = []
    if isinstance(records, list):
        for rec in records:
            if isinstance(rec, list) and len(rec) == 4:
                boxes.append({"bbox": [int(v) for v in rec]})
                continue
            if isinstance(rec, dict):
                bbox = rec.get("barline_location") or rec.get("orig_bbox") or rec.get("pred_bbox")
                if bbox and len(bbox) == 4:
                    entry = {"bbox": [int(v) for v in bbox]}
                    if rec.get("barline_type") or rec.get("type"):
                        entry["barline_type"] = rec.get("barline_type") or rec.get("type")
                    boxes.append(entry)
    return boxes


def group_and_sort_boxes(boxes: list[dict], y_threshold: int) -> list[dict]:
    grouped: list[list[dict]] = []
    for item in boxes:
        box = item["bbox"]
        y_center = (box[1] + box[3]) / 2.0
        for group in grouped:
            ref = group[0]["bbox"]
            ref_y = (ref[1] + ref[3]) / 2.0
            if abs(y_center - ref_y) < y_threshold:
                group.append(item)
                break
        else:
            grouped.append([item])

    for group in grouped:
        group.sort(key=lambda b: b["bbox"][0])

    sorted_records = []
    measure_number = 1
    for group in grouped:
        for item in group:
            box = item["bbox"]
            sorted_records.append(
                {
                    "measure_number": measure_number,
                    "number_location": [0, 0, 0, 0],
                    "barline_location": [int(v) for v in box],
                    "barline_type": item.get("barline_type", "barline"),
                }
            )
            measure_number += 1
    return sorted_records


def normalize_gt_records(boxes: list[dict]) -> list[dict]:
    return [
        {
            "measure_number": 0,
            "number_location": [0, 0, 0, 0],
            "barline_location": [int(v) for v in item["bbox"]],
            "barline_type": item.get("barline_type", "barline"),
        }
        for item in boxes
    ]


def parse_payload_boxes(payload: list) -> list[dict]:
    boxes: list[dict] = []
    for item in payload:
        if isinstance(item, dict):
            bbox = item.get("bbox") or item.get("barline_location") or item.get("orig_bbox") or item.get("pred_bbox")
            if bbox and len(bbox) == 4:
                entry = {"bbox": tuple(int(v) for v in bbox)}
                if item.get("barline_type") or item.get("type"):
                    entry["barline_type"] = item.get("barline_type") or item.get("type")
                boxes.append(entry)
        elif isinstance(item, list) and len(item) == 4:
            boxes.append({"bbox": tuple(int(v) for v in item)})
    return boxes


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            if self.server.mode == "relabel":
                ui = "index.html"
            elif self.server.mode == "rest":
                ui = "index_rest.html"
            else:
                ui = "index_gt.html"
            self._serve_file(self.server.ui_root / ui)
            return
        if parsed.path == "/app.js":
            self._serve_file(self.server.ui_root / "app.js")
            return
        if parsed.path == "/app_gt.js":
            self._serve_file(self.server.ui_root / "app_gt.js")
            return
        if parsed.path == "/app_rest.js":
            self._serve_file(self.server.ui_root / "app_rest.js")
            return
        if parsed.path == "/api/items":
            items = scan_items(self.server.root)
            payload = [item_payload(item, self.server.root) for item in items]
            self._serve_json({"items": payload})
            return
        if parsed.path == "/api/pages" and self.server.mode in {"gt", "rest"}:
            self._serve_json({"pages": self.server.gt_config})
            return
        if parsed.path == "/api/boxes":
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
            boxes = load_boxes(path)
            self._serve_json({"boxes": boxes})
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
        if parsed.path == "/api/probe_log":
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8"))
            page = payload.get("page", "unknown")
            probe = payload.get("probe", {})
            record = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "page": page,
                "probe": probe,
                "selected": payload.get("selected"),
            }
            log_dir = (self.server.root / "logs" / "gt_probe").resolve()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{page}_probe_log.jsonl"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            self._serve_json({"path": str(log_path), "status": "ok"})
            return
        if parsed.path != "/api/save":
            self.send_error(404, "Not found")
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body.decode("utf-8"))
        if self.server.mode == "gt":
            page = payload.get("page")
            boxes = payload.get("boxes", [])
            if not page:
                self.send_error(400, "Missing page")
                return
            config = next((p for p in self.server.gt_config if p["name"] == page), None)
            if not config:
                self.send_error(404, "Unknown page")
                return
            raw_path = safe_path(self.server.root, config["output_raw"])
            sorted_path = safe_path(self.server.root, config["output_sorted"])
            parsed_boxes = parse_payload_boxes(boxes)
            raw_records = normalize_gt_records(parsed_boxes)
            sorted_records = group_and_sort_boxes(
                parsed_boxes,
                int(config.get("y_threshold", 50)),
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            sorted_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(raw_records, indent=2))
            sorted_path.write_text(json.dumps(sorted_records, indent=2))
            self._serve_json({"raw": str(raw_path), "sorted": str(sorted_path), "count": len(boxes)})
            return
        if self.server.mode == "rest":
            page = payload.get("page")
            overrides = payload.get("overrides", [])
            if not page:
                self.send_error(400, "Missing page")
                return
            config = next((p for p in self.server.gt_config if p["name"] == page), None)
            if not config:
                self.send_error(404, "Unknown page")
                return
            output_path = safe_path(self.server.root, config["output"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps({"page": page, "overrides": overrides}, indent=2))
            self._serve_json({"output": str(output_path), "count": len(overrides)})
            return

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
    parser.add_argument("--root", type=Path)
    parser.add_argument("--mode", choices=["relabel", "gt", "rest"], default="relabel")
    parser.add_argument("--config", type=Path, help="GT editor config JSON (gt mode)")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    server.ui_root = Path(__file__).resolve().parent
    server.mode = args.mode
    if args.mode in {"gt", "rest"}:
        if not args.config:
            raise SystemExit("--config is required in gt/rest mode")
        server.root = (args.root or REPO_ROOT).resolve()
        config_data = json.loads(args.config.read_text())
        server.gt_config = config_data.get("pages", config_data)
    else:
        if not args.root:
            raise SystemExit("--root is required in relabel mode")
        server.root = args.root.resolve()

    if args.mode == "gt":
        mode_label = "GT editor"
    elif args.mode == "rest":
        mode_label = "Multi-rest GT editor"
    else:
        mode_label = "GT relabel"
    print(f"{mode_label} GUI running: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
