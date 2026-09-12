from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tools.issue294 import run_full68_refresh_experiment_hosttests as wrapper
from tools.issue294 import run_full68_refresh_experiment_safeio as safeio


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
        wrapper.driver.PROJECT_ROOT / "tools/issue294/run_full68_refresh_experiment_hosttests.py",
        wrapper.driver.PROJECT_ROOT / "tools/issue294/run_full68_refresh_experiment_safeio.py",
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


def test_safeio_shared_paths_accept_same_host_container_resolution(tmp_path, monkeypatch) -> None:
    manager = tmp_path / "manager"
    worktree = tmp_path / "issue294"
    (manager / "temp").mkdir(parents=True)
    (manager / "logs").mkdir()
    worktree.mkdir()
    (worktree / "temp").symlink_to(manager / "temp")
    (worktree / "logs").symlink_to(manager / "logs")

    monkeypatch.setattr(safeio.driver, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(safeio, "_BASE_CONTAINER_STEP", lambda: {"workspace_roundtrip": True})

    def fake_capture(arguments):
        name = arguments[-1].removeprefix("/workspace/")
        return str((manager / name).resolve())

    monkeypatch.setattr(safeio.driver, "_docker_capture", fake_capture)
    result = safeio._container_and_shared_path_step()

    assert result["workspace_roundtrip"] is True
    assert result["shared_output_paths"]["temp"]["resolved"] == str((manager / "temp").resolve())
    assert result["shared_output_paths"]["logs"]["resolved"] == str((manager / "logs").resolve())


def test_safeio_shared_paths_reject_container_broken_relative_link(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    manager = home / "ws_PDFScoreBar"
    worktree = home / "ws_PDFScoreBar_issue294"
    (manager / "temp").mkdir(parents=True)
    (manager / "logs").mkdir()
    worktree.mkdir()
    (worktree / "temp").symlink_to("../ws_PDFScoreBar/temp")
    (worktree / "logs").symlink_to(manager / "logs")

    monkeypatch.setattr(safeio.driver, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(safeio, "_BASE_CONTAINER_STEP", lambda: {"workspace_roundtrip": True})

    def fake_capture(arguments):
        if arguments[-1] == "/workspace/temp":
            raise RuntimeError("readlink -f failed")
        return str((manager / "logs").resolve())

    monkeypatch.setattr(safeio.driver, "_docker_capture", fake_capture)
    with pytest.raises(RuntimeError, match="shared output path is not resolvable") as exc_info:
        safeio._container_and_shared_path_step()

    message = str(exc_info.value)
    assert "link_target='../ws_PDFScoreBar/temp'" in message
    assert str((manager / "temp").resolve()) in message
