#!/usr/bin/env python3
"""Temporary Issue #296 wrapper to rescore the frozen matched guards.

Delete before PR preparation.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import tools.issue296.build_matched_guard_set as guards


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    checkpoint = args.checkpoint.resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)

    guards.CHECKPOINT = checkpoint
    guards.OUT = args.output.resolve()
    return int(guards.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
