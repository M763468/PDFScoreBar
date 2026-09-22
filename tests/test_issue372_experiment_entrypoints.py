"""Regression tests for Issue #372 experiment entrypoints."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _assert_direct_help_succeeds(script: Path, *, cwd: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"usage: {script.name}" in result.stdout
    assert "Traceback" not in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_compare_retained_detector_contracts_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/compare_retained_detector_contracts.py",
        cwd=tmp_path,
    )


def test_materialize_issue43_outputs_direct_entrypoint(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/materialize_issue43_production_outputs.py",
        cwd=tmp_path,
    )


def test_trace_retained_candidate_losses_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/trace_retained_candidate_losses.py",
        cwd=tmp_path,
    )


def test_trace_retained_hybrid_components_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/trace_retained_hybrid_components.py",
        cwd=tmp_path,
    )


def test_run_retained_x4_gap_counterfactual_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/run_retained_x4_gap_counterfactual.py",
        cwd=tmp_path,
    )


def test_resume_x4_gap_counterfactual_evaluation_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/resume_x4_gap_counterfactual_evaluation.py",
        cwd=tmp_path,
    )


def test_attribute_retained_residuals_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/attribute_retained_residuals.py",
        cwd=tmp_path,
    )


def test_clarify_retained_residuals_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/clarify_retained_residuals.py",
        cwd=tmp_path,
    )


def test_screen_retained_x4_injection_boundaries_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/screen_retained_x4_injection_boundaries.py",
        cwd=tmp_path,
    )


def test_inspect_merged_double_x4_geometry_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/inspect_merged_double_x4_geometry.py",
        cwd=tmp_path,
    )


def test_trace_merged_double_d27_current_geometry_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/trace_merged_double_d27_current_geometry.py",
        cwd=tmp_path,
    )


def test_screen_retained_row_gap_promotion_direct_entrypoint_bootstraps_repo(
    tmp_path: Path,
) -> None:
    _assert_direct_help_succeeds(
        ROOT / "experiments/issue372/screen_retained_row_gap_promotion.py",
        cwd=tmp_path,
    )
