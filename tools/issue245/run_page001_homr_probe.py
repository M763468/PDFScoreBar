#!/usr/bin/env python3
"""Resolve the corrected-final page-001 source image and run the Issue #245 HOMR probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_HANDOFF = Path(
    "logs/issue236_pipeline_connected_review_smoke/"
    "source_run/review/manual_correction_input.json"
)
DEFAULT_OUTPUT_ROOT = Path("logs/issue245_focused_homr_probe/page001")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_handoff_image(handoff: Path, page_id: str) -> Path:
    payload = load_json(handoff)
    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    matches = [
        page
        for page in pages
        if isinstance(page, dict) and str(page.get("page_id")) == page_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {page_id!r} entry in {handoff}, found {len(matches)}"
        )
    source_image = matches[0].get("source_image")
    if not isinstance(source_image, str) or not source_image:
        raise ValueError(f"Missing source_image for {page_id!r} in {handoff}")
    image = Path(source_image)
    if not image.is_absolute():
        image = handoff.parent / image
    image = image.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--page-id", default="page_001")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    handoff = (repo_root / args.handoff).resolve()
    if not handoff.is_file():
        raise FileNotFoundError(handoff)
    image = resolve_handoff_image(handoff, args.page_id)

    command = [
        sys.executable,
        "tools/issue245/run_focused_homr_probe.py",
        "probe",
        "--image",
        str(image),
        "--output-root",
        str(args.output_root),
    ]
    if args.force:
        command.append("--force")

    print(f"Handoff: {handoff}")
    print(f"Page: {args.page_id}")
    print(f"Source image: {image}")
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
