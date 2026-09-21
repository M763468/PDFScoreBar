#!/usr/bin/env python3
"""Attach/review-export helpers for Issue #346 movement boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline.review.movement_boundary_review import (
    DEFAULT_RESOLVED_FILENAME,
    DEFAULT_REVIEW_FILENAME,
    attach_movement_boundary_evidence,
    write_resolved_movement_boundaries,
)


def _package_path(package_root: Path, raw: str, *, field: str) -> Path:
    path = Path(raw)
    resolved = (path if path.is_absolute() else package_root / path).resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise ValueError(f"{field} must stay inside the review package") from exc
    return resolved


def _export_from_handoff(handoff_path: Path, *, overwrite: bool) -> dict:
    handoff_path = handoff_path.resolve()
    package_root = handoff_path.parent
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manual correction handoff must be a JSON object")

    evidence_raw = payload.get("movement_boundary_evidence")
    if not isinstance(evidence_raw, str) or not evidence_raw:
        raise ValueError(
            "handoff has no movement_boundary_evidence; run the attach subcommand first"
        )
    resolved_raw = payload.get(
        "movement_boundary_resolved_output",
        f"corrections/{DEFAULT_RESOLVED_FILENAME}",
    )
    if not isinstance(resolved_raw, str) or not resolved_raw:
        raise ValueError("movement_boundary_resolved_output must be a path string")

    evidence_path = _package_path(
        package_root,
        evidence_raw,
        field="movement_boundary_evidence",
    )
    review_path = _package_path(
        package_root,
        f"corrections/{DEFAULT_REVIEW_FILENAME}",
        field="movement boundary review output",
    )
    output_path = _package_path(
        package_root,
        resolved_raw,
        field="movement_boundary_resolved_output",
    )
    return write_resolved_movement_boundaries(
        evidence_path=evidence_path,
        review_path=review_path,
        output_path=output_path,
        evidence_artifact=Path(evidence_raw).as_posix(),
        overwrite=overwrite,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach Issue #333 evidence to a review package or export reviewed #268 boundaries."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    attach = subparsers.add_parser(
        "attach",
        help="Copy movement evidence into an existing review package and update its handoff.",
    )
    attach.add_argument("--handoff", type=Path, required=True)
    attach.add_argument("--evidence", type=Path, required=True)
    attach.add_argument("--overwrite", action="store_true")

    export = subparsers.add_parser(
        "export",
        help="Export explicitly reviewed boundaries from the package to issue268.movement_boundaries.v1.",
    )
    export.add_argument("--handoff", type=Path, required=True)
    export.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    if args.command == "attach":
        updated = attach_movement_boundary_evidence(
            handoff_path=args.handoff,
            evidence_path=args.evidence,
            overwrite=args.overwrite,
        )
        print(
            json.dumps(
                {
                    "handoff": str(args.handoff),
                    "movement_boundary_evidence": updated["movement_boundary_evidence"],
                },
                indent=2,
            )
        )
        return

    resolved = _export_from_handoff(args.handoff, overwrite=args.overwrite)
    print(json.dumps(resolved, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
