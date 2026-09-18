#!/usr/bin/env python3
"""Run investigation-only full-page OCR with model/runtime provenance."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR

from movement_features import image_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--scores", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    requested = set(args.scores)
    engine = RapidOCR()
    pages = []
    for source in fixture["sources"]:
        score = source["score"]
        if score not in requested:
            continue
        for source_page in source["evaluated_pages"]:
            page_id = f"page_{source_page + 1:03d}"
            image = image_path(score, page_id)
            result, _ = engine(str(image))
            entries = [
                {
                    "box": [[round(float(x), 2), round(float(y), 2)] for x, y in box],
                    "text": text,
                    "ocr_score": round(float(score_value), 5),
                }
                for box, text, score_value in (result or [])
            ]
            pages.append(
                {
                    "score": score,
                    "source_page": source_page,
                    "page_id": page_id,
                    "image": str(image),
                    "image_sha256": sha256(image),
                    "ocr": entries,
                }
            )
    package = Path(importlib.metadata.distribution("rapidocr-onnxruntime").locate_file(""))
    models = sorted(package.glob("rapidocr_onnxruntime/models/*.onnx"))
    payload = {
        "schema_version": "issue333.ocr_evidence.v1",
        "runtime": {
            "package": "rapidocr-onnxruntime",
            "version": importlib.metadata.version("rapidocr-onnxruntime"),
            "models": [{"path": str(path), "sha256": sha256(path)} for path in models],
        },
        "pages": pages,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
