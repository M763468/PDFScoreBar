"""Shared feature extraction for Issue 333 experiments (not production code)."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from statistics import median


DEV_ROOT = Path("logs/issue333/fresh/runs")
HOLDOUT_ROOT = Path("logs/issue333/phase2/runs")
HOLDOUT = {"beethoven9", "toy_symphony"}
TEMPO = re.compile(
    r"\b(?:adagio|allegro|andante|larghetto|lento|moderato|presto|prestissimo|"
    r"vivace|vivacissimo|grave|largo)\b",
    re.IGNORECASE,
)
ORDINAL = re.compile(r"(?:^|\s)(?:ii|iii|iv|v|Ⅱ|Ⅲ|Ⅳ|Ⅴ)[.]?(?:\s|$)", re.IGNORECASE)
FORM = re.compile(
    r"\b(?:finale|gavotte|menuett|menuetto|minuet|scherzo|intermezzo)\b",
    re.IGNORECASE,
)
TRIO = re.compile(r"\btrio\b", re.IGNORECASE)


def artifact_path(score: str, page_id: str) -> Path:
    if score in HOLDOUT:
        root = HOLDOUT_ROOT / f"issue333_phase2_{score}"
    else:
        root = DEV_ROOT / score
    return root / "intermediate" / page_id / "numbering_base.json"


def image_path(score: str, page_id: str) -> Path:
    if score in HOLDOUT:
        root = HOLDOUT_ROOT / f"issue333_phase2_{score}"
    else:
        root = DEV_ROOT / score
    return root / "inputs" / "images" / f"{page_id}.png"


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def load_ocr(path: Path) -> dict[tuple[str, str], list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {(page["score"], page["page_id"]): page["ocr"] for page in payload["pages"]}


def build_rows(fixture_path: Path, ocr_path: Path, scores: set[str]) -> list[dict]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    truth = {
        (item["score"], item["page_id"], item["system"])
        for item in fixture["boundaries"]
    }
    ocr = load_ocr(ocr_path)
    rows = []
    for source in fixture["sources"]:
        score = source["score"]
        if score not in scores:
            continue
        for source_page in source["evaluated_pages"]:
            page_id = f"page_{source_page + 1:03d}"
            page = json.loads(
                artifact_path(score, page_id).read_text(encoding="utf-8")
            )["pages"][0]
            systems = page["systems"]
            if not systems:
                continue
            boxes = [system["staves"][0]["bbox"] for system in systems]
            gaps = [boxes[index][1] - boxes[index - 1][3] for index in range(1, len(boxes))]
            gap_median = median(gaps) if gaps else 0.0
            left_median = median(box[0] for box in boxes)
            page_ocr_heights = [
                max(point[1] for point in item["box"])
                - min(point[1] for point in item["box"])
                for item in ocr.get((score, page_id), [])
            ]
            ocr_height_median = median(page_ocr_heights) if page_ocr_heights else 1.0
            for index, box in enumerate(boxes):
                previous_bottom = boxes[index - 1][3] if index else 0
                system_height = max(1, box[3] - box[1])
                associated = []
                for item in ocr.get((score, page_id), []):
                    y_values = [point[1] for point in item["box"]]
                    center_y = sum(y_values) / len(y_values)
                    if previous_bottom - 0.005 * page["height"] <= center_y <= box[1] + 0.25 * system_height:
                        associated.append(item)
                texts = [normalize_text(item["text"]) for item in associated]
                text = " | ".join(texts)
                heights = [
                    max(point[1] for point in item["box"])
                    - min(point[1] for point in item["box"])
                    for item in associated
                ]
                gap = gaps[index - 1] if index else box[1]
                gap_ratio = gap / gap_median if index and gap_median else 1.0
                indent_ratio = (box[0] - left_median) / page["width"]
                geometry_candidate = indent_ratio >= 0.02 or (index > 0 and gap_ratio >= 1.75)
                has_tempo = bool(TEMPO.search(text))
                has_ordinal = bool(ORDINAL.search(f" {text} "))
                has_form = bool(FORM.search(text))
                has_trio = bool(TRIO.search(text))
                semantic_heading = has_tempo or has_ordinal or has_form
                location = (score, page_id, index)
                rows.append(
                    {
                        "score": score,
                        "source_page": source_page,
                        "page_id": page_id,
                        "system": index,
                        "label": int(location in truth),
                        "ocr_text": text,
                        "raw_ocr": associated,
                        "features": {
                            "page_start": int(index == 0),
                            "system_index_ratio": index / max(1, len(boxes) - 1),
                            "top_ratio": box[1] / page["height"],
                            "left_ratio": box[0] / page["width"],
                            "indent_ratio": indent_ratio,
                            "gap_page_ratio": gap / page["height"],
                            "gap_median_ratio": gap_ratio,
                            "system_height_ratio": system_height / page["height"],
                            "system_width_ratio": (box[2] - box[0]) / page["width"],
                            "measure_count": len(systems[index]["measures"]),
                            "ocr_count": len(associated),
                            "max_ocr_height_to_page_median": (
                                max(heights) / ocr_height_median if heights else 0.0
                            ),
                            "has_tempo": int(has_tempo),
                            "has_ordinal": int(has_ordinal),
                            "has_form": int(has_form),
                            "has_trio": int(has_trio),
                            "semantic_heading": int(semantic_heading),
                            "geometry_candidate": int(geometry_candidate),
                            "structured_consensus": int(geometry_candidate and semantic_heading),
                        },
                    }
                )
    return rows

