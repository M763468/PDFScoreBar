#!/usr/bin/env python3
"""Compatibility wrapper for the Issue #274 existing-mechanism matrix.

The original experiment used the wrong retained thin-replay directory name in its
module-level default.  Keep the original commit as forensic history and patch only
the input path here; all analysis logic remains in
``analyze_existing_mechanism_structural_matrix.py``.
"""
from __future__ import annotations

from pathlib import Path

from tools.issue274 import analyze_existing_mechanism_structural_matrix as impl

impl.THIN_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/thin_policy_replay_01/"
    "issue274_thin_policy_single_inference_replay.json"
)

if __name__ == "__main__":
    raise SystemExit(impl.main())
