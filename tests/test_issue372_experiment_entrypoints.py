"""Regression tests for Issue #372 experiment entrypoints."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compare_retained_detector_contracts_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    script = ROOT / "experiments/issue372/compare_retained_detector_contracts.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Issue #372 retained-only detector regression comparison" in result.stdout


def test_materialize_issue43_outputs_direct_entrypoint(
    tmp_path: Path,
) -> None:
    script = ROOT / "experiments/issue372/materialize_issue43_production_outputs.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Materialize Issue #43 saved production detector JSONs" in result.stdout
