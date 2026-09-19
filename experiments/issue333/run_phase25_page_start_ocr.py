#!/usr/bin/env python3
"""Extract investigation-only page-start heading evidence for Issue #333."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import unicodedata
from pathlib import Path

import cv2
from rapidocr_onnxruntime import RapidOCR

TEMPO = re.compile(
    r"\b(?:adagio|allegretto|allegro|andante|larghetto|largo|lento|moderato|"
    r"prestissimo|presto|vivace|vivacissimo)\b",
    re.IGNORECASE,
)
ORDINAL = re.compile(r"(?:^|\s)(?:ii|iii|iv|v|Ⅱ|Ⅲ|Ⅳ|Ⅴ)[.]?(?:\s|$)", re.IGNORECASE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def _numbering(root: Path, page_id: str) -> dict:
    path = root / "intermediate" / page_id / "numbering_base.json"
    return json.loads(path.read_text(encoding="utf-8"))["pages"][0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--evaluation2-images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    engine = RapidOCR()
    pages = []
    for source in corpus["sources"]:
        score = source["score"]
        run = next(item for item in runs["runs"] if item["score"] == score)
        root = Path(run["root"])
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for ordered_page, (source_page, manifest_page) in enumerate(
            zip(source["musical_source_pages"], manifest["pages"], strict=True)
        ):
            page_id = manifest_page["page_id"]
            local_image = root / "inputs" / "images" / f"{page_id}.png"
            if local_image.is_file():
                image_path = local_image
            else:
                image_path = args.evaluation2_images / root.name / f"{page_id}.png"
            image = cv2.imread(str(image_path))
            if image is None:
                raise FileNotFoundError(image_path)
            numbering = _numbering(root, page_id)
            if not numbering["systems"]:
                continue
            first_staves = numbering["systems"][0]["staves"]
            bottom = max(staff["bbox"][3] for staff in first_staves)
            system_height = bottom - min(staff["bbox"][1] for staff in first_staves)
            crop_bottom = min(image.shape[0], int(round(bottom + 0.25 * system_height)))
            crop = image[:crop_bottom, :]
            result, _ = engine(crop)
            entries = [
                {
                    "box": [[round(float(x), 2), round(float(y), 2)] for x, y in box],
                    "text": text,
                    "ocr_score": round(float(ocr_score), 6),
                }
                for box, text, ocr_score in (result or [])
            ]
            text = " | ".join(_normalize(item["text"]) for item in entries)
            has_ordinal = bool(ORDINAL.search(f" {text} "))
            has_tempo = bool(TEMPO.search(text))
            pages.append(
                {
                    "score": score,
                    "page": ordered_page,
                    "source_page": source_page,
                    "page_id": page_id,
                    "image": str(image_path),
                    "image_sha256": _sha256(image_path),
                    "crop": [0, 0, image.shape[1], crop_bottom],
                    "ocr": entries,
                    "normalized_text": text,
                    "has_exact_ordinal": has_ordinal,
                    "has_exact_tempo": has_tempo,
                    "exact_ordinal_tempo_candidate": bool(
                        ordered_page > 0 and has_ordinal and has_tempo
                    ),
                }
            )
    package = Path(importlib.metadata.distribution("rapidocr-onnxruntime").locate_file(""))
    models = sorted(package.glob("rapidocr_onnxruntime/models/*.onnx"))
    output = {
        "schema_version": "issue333.page_start_ocr_evidence.v1",
        "strategy": {
            "candidate": "non-initial page start with exact Roman ordinal AND exact tempo token",
            "crop": "page top through 0.25 reconstructed first-system union height below its bottom",
            "selection_locked_before_results": True,
            "role": "investigation-only evidence; does not modify MMR OCR semantics",
        },
        "runtime": {
            "package": "rapidocr-onnxruntime",
            "version": importlib.metadata.version("rapidocr-onnxruntime"),
            "models": [{"path": str(path), "sha256": _sha256(path)} for path in models],
        },
        "pages": pages,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
