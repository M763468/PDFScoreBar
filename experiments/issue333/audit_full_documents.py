#!/usr/bin/env python3
"""Render reproducible low-resolution contact sheets for Issue #333 GT audit.

The rendered pages are investigation artifacts and must remain below ignored
``logs/issue333``.  The script records source hashes and physical PDF indices;
it does not infer pipeline input indices or movement labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import fitz
import numpy as np


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render(page: fitz.Page, width: int) -> np.ndarray:
    scale = width / page.rect.width
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--thumb-width", type=int, default=500)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    sources = []
    for source in corpus["sources"]:
        matches = list(args.pdf_root.rglob(source["pdf_filename"]))
        if len(matches) != 1:
            raise ValueError(f"expected one PDF for {source['score']}, found {matches}")
        pdf_path = matches[0]
        digest = _sha256(pdf_path)
        if digest != source["sha256"]:
            raise ValueError(f"source digest mismatch: {source['score']}")
        score_dir = args.output / source["score"]
        score_dir.mkdir(exist_ok=True)
        thumbnails = []
        page_records = []
        with fitz.open(pdf_path) as document:
            for source_page, page in enumerate(document):
                image = _render(page, args.thumb_width)
                cv2.putText(
                    image,
                    f"source_page={source_page} pdf_page={source_page + 1}",
                    (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
                page_path = score_dir / f"source_page_{source_page:03d}.jpg"
                if not cv2.imwrite(str(page_path), image):
                    raise OSError(f"could not write {page_path}")
                thumbnails.append(image)
                page_records.append(
                    {
                        "source_page": source_page,
                        "pdf_page_number": source_page + 1,
                        "artifact": str(page_path),
                    }
                )
        tile_height = max(image.shape[0] for image in thumbnails)
        rows = (len(thumbnails) + args.columns - 1) // args.columns
        sheet = np.full(
            (rows * tile_height, args.columns * args.thumb_width, 3), 255, dtype=np.uint8
        )
        for index, image in enumerate(thumbnails):
            y = index // args.columns * tile_height
            x = index % args.columns * args.thumb_width
            sheet[y : y + image.shape[0], x : x + image.shape[1]] = image
        sheet_path = args.output / f"{source['score']}_contact_sheet.jpg"
        if not cv2.imwrite(str(sheet_path), sheet):
            raise OSError(f"could not write {sheet_path}")
        sources.append(
            {
                "score": source["score"],
                "pdf_filename": pdf_path.name,
                "sha256": digest,
                "page_count": len(page_records),
                "contact_sheet": str(sheet_path),
                "pages": page_records,
            }
        )
    output = {
        "schema_version": "issue333.full_document_audit_artifacts.v1",
        "coordinate_system": {
            "source_page": "zero-based physical PDF page",
            "pdf_page_number": "one-based human-readable physical PDF page",
        },
        "sources": sources,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
