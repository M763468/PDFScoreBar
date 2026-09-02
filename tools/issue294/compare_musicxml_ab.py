#!/usr/bin/env python3
"""Compare MusicXML emitted by the Issue #294 same-original A/B run."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

STRUCTURAL_TAGS = (
    "score-partwise",
    "score-timewise",
    "part",
    "measure",
    "note",
    "rest",
    "barline",
    "attributes",
    "clef",
    "staff",
    "backup",
    "forward",
    "direction",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_musicxml(detection_path: Path) -> Path:
    directory = detection_path.resolve().parent
    candidates = sorted(
        path
        for pattern in ("*.musicxml", "*.xml")
        for path in directory.glob(pattern)
        if path.is_file()
    )
    if not candidates:
        raise FileNotFoundError(f"No MusicXML next to detection artifact: {detection_path}")
    musicxml = [path for path in candidates if path.suffix.lower() == ".musicxml"]
    if len(musicxml) == 1:
        return musicxml[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        "Ambiguous MusicXML artifacts next to detection artifact: "
        + ", ".join(str(path) for path in candidates)
    )


def summarize_musicxml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    counts = Counter(_local_name(element.tag) for element in root.iter())
    canonical = ET.canonicalize(
        xml_data=raw.decode("utf-8"),
        strip_text=True,
        rewrite_prefixes=True,
    ).encode("utf-8")
    return {
        "path": str(path.resolve()),
        "raw_sha256": sha256_bytes(raw),
        "canonical_sha256": sha256_bytes(canonical),
        "raw_bytes": len(raw),
        "root_tag": _local_name(root.tag),
        "structural_counts": {tag: int(counts.get(tag, 0)) for tag in STRUCTURAL_TAGS},
        "all_element_count": int(sum(counts.values())),
    }


def compare_musicxml(left: Path, right: Path) -> dict[str, Any]:
    a = summarize_musicxml(left)
    b = summarize_musicxml(right)
    return {
        "A_pinned": a,
        "B_maintained": b,
        "raw_equal": a["raw_sha256"] == b["raw_sha256"],
        "canonical_equal": a["canonical_sha256"] == b["canonical_sha256"],
        "root_tag_equal": a["root_tag"] == b["root_tag"],
        "structural_counts_equal": a["structural_counts"] == b["structural_counts"],
        "all_element_count_delta": b["all_element_count"] - a["all_element_count"],
    }


def _detection_path(page: dict[str, Any], variant: str) -> Path:
    payload = page.get(variant)
    if not isinstance(payload, dict):
        raise ValueError(f"Page summary lacks {variant}")
    if variant == "A_pinned":
        artifacts = payload.get("artifacts")
    else:
        worker = payload.get("worker")
        if not isinstance(worker, dict):
            raise ValueError("Page summary lacks maintained worker payload")
        artifacts = worker.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("detections"):
        raise ValueError(f"Page summary lacks {variant} detections")
    return Path(str(artifacts["detections"]))


def run(summary_path: Path, output: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    if not isinstance(summary, dict) or summary.get("status") != "completed":
        raise ValueError(f"Invalid A/B summary: {summary_path}")
    pages_payload = summary.get("pages")
    if not isinstance(pages_payload, list) or not pages_payload:
        raise ValueError("A/B summary has no pages")

    pages: list[dict[str, Any]] = []
    for page in pages_payload:
        if not isinstance(page, dict):
            raise ValueError("A/B summary contains invalid page entry")
        a_detection = _detection_path(page, "A_pinned")
        b_detection = _detection_path(page, "B_maintained")
        result = compare_musicxml(
            find_musicxml(a_detection),
            find_musicxml(b_detection),
        )
        result["image"] = page.get("image")
        pages.append(result)

    canonical_equal_all = all(page["canonical_equal"] for page in pages)
    structural_equal_all = all(page["structural_counts_equal"] for page in pages)
    report = {
        "schema_version": "issue294.same_original_musicxml_comparison.v1",
        "status": "completed",
        "summary": str(summary_path.resolve()),
        "pages": pages,
        "aggregate": {
            "page_count": len(pages),
            "raw_equal_all": all(page["raw_equal"] for page in pages),
            "canonical_equal_all": canonical_equal_all,
            "structural_counts_equal_all": structural_equal_all,
            "semantic_review_required": not canonical_equal_all,
        },
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.summary, args.output)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "completed", "output": str(args.output.resolve()), "aggregate": report["aggregate"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
