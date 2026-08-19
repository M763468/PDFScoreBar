#!/usr/bin/env python3
"""Compatibility wrapper for Issue #274 structural crop rendering.

The original renderer writes all PNG panels successfully and then failed while
writing its JSON report because `write_json` was accidentally omitted.  Keep the
original experiment intact and inject the missing writer here so the retained
forensic record remains reproducible without changing the rendering logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.issue274 import render_stage_e_structural_identity_crops as impl


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


impl.write_json = write_json

if __name__ == "__main__":
    raise SystemExit(impl.main())
