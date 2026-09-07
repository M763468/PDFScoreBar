from __future__ import annotations

import os
import subprocess
import sys

from tools.issue294 import run_full68_refresh_experiment_hosttests as wrapper


def test_host_targeted_tests_use_invoking_python(monkeypatch) -> None:
    observed = {}

    class Completed:
        returncode = 0

    def fake_run(command, *, cwd, env, check):
        observed["command"] = command
        observed["cwd"] = cwd
        observed["env"] = env
        observed["check"] = check
        return Completed()

    monkeypatch.setattr(wrapper.driver.subprocess, "run", fake_run)
    result = wrapper._host_tests_step()

    assert observed["command"][:3] == [sys.executable, "-m", "pytest"]
    assert observed["cwd"] == wrapper.driver.PROJECT_ROOT
    assert observed["check"] is False
    assert str(wrapper.driver.PROJECT_ROOT) in observed["env"]["PYTHONPATH"].split(os.pathsep)
    assert result["execution_environment"] == "host_test_venv"
    assert result["python"] == sys.executable


def test_experiment_wrappers_support_direct_execution_outside_repo(tmp_path) -> None:
    scripts = [
        wrapper.driver.PROJECT_ROOT
        / "tools/issue294/run_full68_refresh_experiment_hosttests.py",
        wrapper.driver.PROJECT_ROOT
        / "tools/issue294/run_full68_refresh_experiment_safeio.py",
    ]
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=tmp_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert completed.returncode == 0, (
            f"direct execution failed for {script}:\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
