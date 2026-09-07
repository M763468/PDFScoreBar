from __future__ import annotations

import os
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
