#!/usr/bin/env python3
"""One-command entrypoint for Issue #264 Phase B page_001 acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.utils.io import load_json
from tools.issue264.phase_b_page001_acceptance import run

CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"


def resolve_manifest(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(explicit)
        return explicit

    candidates = [
        Path("logs/full_pipeline_runs") / CANONICAL_RUN / "manifest.json",
        Path("logs") / CANONICAL_RUN / "manifest.json",
    ]
    candidates.extend(Path("logs").glob(f"**/{CANONICAL_RUN}/manifest.json"))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        payload = load_json(candidate)
        if payload.get("run_id") == CANONICAL_RUN:
            return candidate
    raise FileNotFoundError(
        "Canonical detector manifest was not found. Use --detector-manifest PATH."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector-manifest", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue264_phase_b_acceptance"),
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    args = parser.parse_args()
    manifest = resolve_manifest(args.detector_manifest)
    report = run(manifest, args.output_root / args.run_id)
    return 0 if load_json(report).get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
