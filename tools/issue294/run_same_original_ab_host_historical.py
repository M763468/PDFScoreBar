#!/usr/bin/env python3
"""Host adapter for the historical Stage-E artifact contract in Issue #294."""

from __future__ import annotations

from pathlib import Path

from tools.issue294 import run_same_original_ab_host as base

_REWRITES = {
    "tools/issue294/run_same_original_ab.py": "tools/issue294/run_same_original_ab_historical.py",
    "tools/issue294/compare_same_original_ab.py": "tools/issue294/compare_same_original_ab_historical.py",
}
_ORIGINAL_CHECKED = base.checked


def _historical_checked(command: list[str], *, cwd: Path | None = None) -> None:
    rewritten = [_REWRITES.get(part, part) for part in command]
    _ORIGINAL_CHECKED(rewritten, cwd=cwd)


def run(run_tag: str, pages: list[str], support_root: Path | None = None) -> dict[str, str]:
    previous = base.checked
    base.checked = _historical_checked
    try:
        return base.run(run_tag, pages, support_root)
    finally:
        base.checked = previous


# Re-export values used by the complete host gate.
CONTAINER = base.CONTAINER
CONTAINER_ROOT = base.CONTAINER_ROOT
PIPELINE_PYTHON = base.PIPELINE_PYTHON
PROJECT_ROOT = base.PROJECT_ROOT
