#!/usr/bin/env python3
"""Run Issue #294 A/B using the actual historical Stage-E artifact names.

The underlying A/B implementation and the pinned Stage-E command are unchanged.
This compatibility entrypoint only replaces the post-run artifact resolver for
variant A: the historical evaluator materializes detections plus diagnostic mask
overlays, not the raw ``*_staff_mask.png``/``*_notehead_mask.png`` files emitted
by the maintained worker.
"""

from __future__ import annotations

import os
from pathlib import Path

from tools.issue294 import run_same_original_ab as base

SOURCE_COMMIT_ENV = "ISSUE294_SOURCE_COMMIT"


def historical_artifact_paths(root: Path, stem: str) -> dict[str, str]:
    run_dir = root / "batch" / stem
    return {
        "detections": str(run_dir / f"{stem}_detections.json"),
        "staff_overlay": str(run_dir / f"{stem}_debug_staff_resized_overlay.png"),
        "notehead_overlay": str(run_dir / f"{stem}_debug_notehead_resized_overlay.png"),
    }


def host_supplied_source_commit() -> str | None:
    value = os.environ.get(SOURCE_COMMIT_ENV, "").strip()
    if value:
        return value
    return base._source_commit()


def main() -> int:
    base._artifact_paths = historical_artifact_paths
    base._source_commit = host_supplied_source_commit
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
