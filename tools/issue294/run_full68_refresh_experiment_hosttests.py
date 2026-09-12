#!/usr/bin/env python3
"""Run the Issue #294 full68 experiment with tests in the host test environment.

Temporary experiment-only compatibility wrapper. The profiling container is a
production runtime and intentionally does not contain pytest. Keep inference,
SR, HOMR, CNN and MMR execution in that container, but run repository regression
tests with the invoking host Python (the Issue #294 .venv_pdf in normal use).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_full68_refresh_experiment as driver


def _host_tests_step() -> dict[str, object]:
    tests = [
        "tests/test_issue294_full68_host.py",
        "tests/test_issue294_full68_mmr_audit.py",
        "tests/test_issue294_downstream_candidate_matrix.py",
        "tests/test_issue294_global_page_host.py",
        "tests/test_issue294_full68_refresh_experiment.py",
        "tests/test_issue294_full68_refresh_experiment_hosttests.py",
    ]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(driver.PROJECT_ROOT)
        if not existing
        else os.pathsep.join([str(driver.PROJECT_ROOT), existing])
    )
    completed = driver.subprocess.run(
        [sys.executable, "-m", "pytest", *tests],
        cwd=driver.PROJECT_ROOT,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Issue #294 host targeted tests failed with return code {completed.returncode}"
        )
    return {
        "tests": tests,
        "returncode": int(completed.returncode),
        "python": sys.executable,
        "execution_environment": "host_test_venv",
    }


def main() -> int:
    driver._tests_step = _host_tests_step
    return driver.main()


if __name__ == "__main__":
    raise SystemExit(main())
