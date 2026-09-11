from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


WRAPPERS = (
    "tools/issue120/run_stage_c_seed_regen_then_eval.py",
    "tools/issue120/run_issue36_dense_candidates_then_eval.py",
    "tools/issue120/run_issue53_probe_rescue_then_eval.py",
)


def test_score_wrapper_contract_flags_reach_each_parser() -> None:
    for script in WRAPPERS:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "--staff-units-json" in result.stdout, script
        assert "--xdist-unit-ratio" in result.stdout, script
        assert "--xdist-threshold" not in result.stdout, script


def test_make_targets_forward_canonical_contract_flags() -> None:
    stage_e = subprocess.run(
        ["make", "-n", "eval-issue120-stage-e-full"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "--staff-units-json data/evaluation2/staff_units.json" in stage_e
    assert "--xdist-unit-ratio 0.5" in stage_e
    assert "--image-root data/evaluation2/images" in stage_e
    assert "--xdist-threshold" not in stage_e

    stage_d = subprocess.run(
        ["make", "-n", "verify-issue120-stage-d"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert '--staff-units-json "data/evaluation2/staff_units.json"' in stage_d
    assert '--xdist-unit-ratio "0.5"' in stage_d
