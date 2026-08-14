#!/usr/bin/env python3
"""One-command entrypoint for Issue #264 Phase B page_001 acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.utils.io import load_json, write_json
from tools.issue264.phase_b_page001_acceptance import run

CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"
TARGET_STEM = "Va_Prokofiev_Symphony1_page_001"
CANONICAL_IMAGE = Path(
    "/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
)
CANONICAL_BARLINES = Path(
    "/workspace/logs/verification/detector_full68/"
    f"{CANONICAL_RUN}/production_runs/Va_Prokofiev_Symphony1/intermediate/"
    "dense_full_pipeline_route/dense_candidate_reconstruction/probe_rescue_candidates/"
    "eval2_Va_Prokofiev_Symphony1_page_001/pipeline2_no_peak_filtered_cnn.json"
)
CANONICAL_STAFF_MASK = Path(
    "/workspace/logs/full_pipeline_runs/dense_full_pipeline/hybrid_output/"
    f"{CANONICAL_RUN}__Va_Prokofiev_Symphony1/sr/batch/page_001/"
    "page_001_proxy_debug_3_staff.png"
)


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


def resolve_manifest(explicit: Path | None) -> Path | None:
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

    return _matching_manifest(list(Path("logs").rglob("manifest.json")))


def materialize_canonical_artifact_manifest(run_dir: Path) -> Path:
    required = [CANONICAL_IMAGE, CANONICAL_BARLINES, CANONICAL_STAFF_MASK]
    missing = [path for path in required if not path.is_file()]
    if missing:
        details = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Canonical detector manifest is absent and required retained artifacts are missing:\n"
            + details
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "canonical_detector_artifacts.json"
    write_json(
        manifest_path,
        {
            "run_id": CANONICAL_RUN,
            "artifact_source": "retained_canonical_detector_artifacts",
            "detector_reexecuted": False,
            "pages": [
                {
                    "page_id": TARGET_STEM,
                    "image_path": str(CANONICAL_IMAGE),
                    "barlines_json": str(CANONICAL_BARLINES),
                    "staff_mask": str(CANONICAL_STAFF_MASK),
                }
            ],
        },
    )
    return manifest_path


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
    run_dir = args.output_root / args.run_id
    manifest = resolve_manifest(args.detector_manifest)
    if manifest is None:
        manifest = materialize_canonical_artifact_manifest(run_dir)
    report = run(manifest, run_dir)
    return 0 if load_json(report).get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
