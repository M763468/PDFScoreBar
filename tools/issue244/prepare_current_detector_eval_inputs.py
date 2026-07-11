#!/usr/bin/env python3
"""Normalize production-run detector artifacts for the full-68 evaluator."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from src.pipeline.core.run_ids import (
    build_probe_run_id,
    split_score_page_from_composite_stem,
)

EXPECTED_PAGES = 68
SCORED_FILE = "pipeline2_no_peak_scored.json"
CANDIDATES_FILE = "pipeline2_no_peak_candidates.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_parts(image_path: Path) -> tuple[str, str]:
    parts = split_score_page_from_composite_stem(image_path.stem)
    if parts is None:
        raise ValueError(f"Cannot derive canonical score/page from {image_path.name}")
    return parts


def materialize(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.run_root / "manifest.json"
    manifest = load_json(manifest_path)
    pages = manifest.get("pages", [])
    if not isinstance(pages, list) or len(pages) != EXPECTED_PAGES:
        raise RuntimeError(
            f"Expected {EXPECTED_PAGES} manifest pages, got {len(pages)}"
        )

    detection = manifest.get("config", {}).get("detection", {})
    score_name = (
        detection.get("probe_score_name") if isinstance(detection, dict) else None
    )

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError(f"Invalid manifest page: {page}")
        image_value = page.get("image_path")
        if not isinstance(image_value, str):
            raise ValueError(f"Manifest page has no image_path: {page}")
        image_path = Path(image_value)
        score, canonical_page = canonical_parts(image_path)
        key = (score, canonical_page)
        if key in seen:
            raise ValueError(
                f"Duplicate canonical page mapping: {score}/{canonical_page}"
            )
        seen.add(key)

        probe_run_id = build_probe_run_id(image_path, score_name=score_name)
        source_dir = args.run_root / "intermediate" / "probe_scan" / probe_run_id
        destination_dir = args.output_dir / f"eval2_{score}_{canonical_page}"
        scored_source = source_dir / SCORED_FILE
        candidates_source = source_dir / CANDIDATES_FILE
        materialize(scored_source, destination_dir / SCORED_FILE)
        materialize(candidates_source, destination_dir / CANDIDATES_FILE)

        records.append(
            {
                "score": score,
                "page": canonical_page,
                "image_path": str(image_path),
                "probe_run_id": probe_run_id,
                "scored_source": str(scored_source),
                "candidates_source": str(candidates_source),
                "eval_input_dir": str(destination_dir),
            }
        )

    mapping_path = args.output_dir / "input_manifest.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema": "issue244.current_detector_eval_inputs.v1",
                "run_root": str(args.run_root),
                "page_count": len(records),
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Prepared current detector eval inputs: {len(records)} pages")
    print(f"Output: {args.output_dir}")
    print(f"Manifest: {mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
