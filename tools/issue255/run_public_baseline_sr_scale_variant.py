#!/usr/bin/env python3
"""Run one public-baseline detector replay with an explicit SR scale.

This is an Issue #255 experiment adapter. It keeps the canonical production
configuration unchanged and overrides only ``detection.sr_scale`` in memory.
"""

from __future__ import annotations

import argparse
import copy
import json
from argparse import Namespace
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import tools.issue255.run_public_baseline_ab_variant as base_variant


def _scaled_config(
    loader: Callable[[Path], Any],
    path: Path,
    sr_scale: int,
) -> dict[str, Any]:
    config = copy.deepcopy(loader(path))
    if not isinstance(config, Mapping):
        raise ValueError("Canonical configuration is not a mapping")
    result = dict(config)
    detection = result.get("detection")
    if not isinstance(detection, Mapping):
        raise ValueError("Canonical configuration lacks detection settings")
    result["detection"] = dict(detection)
    result["detection"]["sr_scale"] = sr_scale
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    original_loader = base_variant.load_yaml

    def load_with_scale(path: Path) -> dict[str, Any]:
        return _scaled_config(original_loader, path, args.sr_scale)

    base_variant.load_yaml = load_with_scale
    try:
        report = base_variant.build_report(
            Namespace(
                variant="public_baseline",
                image=args.image,
                score=args.score,
                page=args.page,
                run_id=args.run_id,
                output_root=args.output_root,
                baseline_handoff=args.baseline_handoff,
            )
        )
    finally:
        base_variant.load_yaml = original_loader

    report["schema_version"] = "issue255.public_baseline_sr_scale_run.v1"
    report["analysis_only"] = True
    report["restoration_scope_only"] = True
    report["sr_scale_override"] = args.sr_scale
    overrides = report.get("execution_only_overrides")
    if not isinstance(overrides, dict):
        raise ValueError("Variant report lacks execution-only overrides")
    overrides["detection.sr_scale"] = args.sr_scale
    report_path = Path(str(report["run_dir"])) / "issue255_public_baseline_ab_run_contract.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sr-scale", type=int, choices=(2, 4), required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--baseline-handoff", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "run_dir": report["run_dir"],
                "sr_scale": report["sr_scale_override"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
