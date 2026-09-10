#!/usr/bin/env python3
"""Run the merged J2 MMR baseline across the same retained full-68 corpus.

This is experiment-only comparison tooling for Issue #277.  It reuses the same
numbering artifacts, MMR support sidecars, classifier, RapidOCR provider and page
loop as ``run_targeted_mmr_full68.py`` but swaps the candidate processor for the
merged production J2 ``MMRProcessor``.  No detector/HOMR/SR/OMR/grouping/numbering
work is rerun.

The profiling image intentionally has no git executable.  Provenance is supplied
from the host Issue #277 worktree through ``ISSUE277_GIT_HEAD``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from src.measure_numbering.mmr import MMRProcessor
from tools.issue277 import run_targeted_mmr_full68 as target
from tools.issue277.run_targeted_mmr_full68_container import resolve_host_git_head

DEFAULT_OUTPUT = (
    target.PROJECT_ROOT
    / "logs/issue277/issue277_j2_full68_reference_01/j2_mmr_full68_reference_01.json"
)


class J2ReferenceProcessor(MMRProcessor):
    """Expose the merged J2 processor through the targeted runner interface."""

    def __init__(self, *, ocr_engine: Any, classifier: Any):
        import torch

        super().__init__(
            Path("unused"),
            torch.device("cpu"),
            classifier=classifier,
            ocr_engine=ocr_engine,
        )
        self.decision_trace: list[dict[str, Any]] = []

    def reset_decision_trace(self) -> None:
        self.decision_trace.clear()

    def _detect_number_with_evidence(self, *args: Any, **kwargs: Any):
        result = super()._detect_number_with_evidence(*args, **kwargs)
        self.decision_trace.append(
            {
                "stage": "merged_j2",
                "selected_num": result[0],
                "selected_score": float(result[1]),
            }
        )
        return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    git_head = resolve_host_git_head(os.environ.get("ISSUE277_GIT_HEAD"))
    original_processor = target.TargetedRetryProcessor
    original_git_head = target._git_head
    target.TargetedRetryProcessor = J2ReferenceProcessor
    target._git_head = lambda: git_head
    try:
        payload = target.run(
            reuse_root=args.reuse_root,
            numbering_root=args.numbering_root,
            model_path=args.model,
            output_path=args.output,
            provider_mode=args.provider,
            preflight_only=args.preflight,
        )
    finally:
        target.TargetedRetryProcessor = original_processor
        target._git_head = original_git_head

    payload["schema_version"] = (
        "issue277.j2_mmr_full68_reference.preflight.v1"
        if args.preflight
        else "issue277.j2_mmr_full68_reference.v1"
    )
    if not args.preflight:
        payload["execution_contract"]["candidate"] = (
            "merged production J2 baseline: low-score <=5 baseline plus x -2/+2 and "
            "all-staff y -2/+2, strict 3/5 majority"
        )
        payload["execution_contract"]["reference_only"] = True
    target._write_json(args.output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-root", type=Path, default=target.DEFAULT_REUSE_ROOT)
    parser.add_argument("--numbering-root", type=Path, default=target.DEFAULT_NUMBERING_ROOT)
    parser.add_argument("--model", type=Path, default=target.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    payload = run(args)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload.get("summary"),
                "runtime": payload.get("runtime"),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
