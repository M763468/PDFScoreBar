#!/usr/bin/env python3
"""One-command entrypoint for Issue #264 Phase B page_001 acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.utils.io import load_json
from tools.issue264.phase_b_page001_acceptance import run

CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"


def _matching_manifest(candidates: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        payload = load_json(candidate)
        if not isinstance(payload, dict):
            continue
        if payload.get("run_id") == CANONICAL_RUN:
            return candidate
    return None


def resolve_manifest(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(explicit)
        return explicit

    direct = [
        Path("logs/full_pipeline_runs") / CANONICAL_RUN / "manifest.json",
        Path("logs") / CANONICAL_RUN / "manifest.json",
    ]
    direct.extend(Path("logs").glob(f"**/{CANONICAL_RUN}/manifest.json"))
    matched = _matching_manifest(direct)
    if matched is not None:
        return matched

    matched = _matching_manifest(list(Path("logs").rglob("manifest.json")))
    if matched is not None:
        return matched
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
