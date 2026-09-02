from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.issue294 import run_same_original_ab_host as host_runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_help(script: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_issue294_complete_host_gate_bootstraps_repo_imports(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "tools/issue294/run_same_original_gate_host.py"

    completed = _run_help(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "--run-tag" in completed.stdout
    assert "--page" in completed.stdout


def test_issue294_recovery_host_gate_bootstraps_repo_imports(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "tools/issue294/finalize_same_original_gate_host.py"

    completed = _run_help(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "--run-tag" in completed.stdout


def test_issue294_host_runner_restores_container_output_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "run"
    output.mkdir()
    commands: list[list[str]] = []

    monkeypatch.setattr(host_runner.os, "getuid", lambda: 1234)
    monkeypatch.setattr(host_runner.os, "getgid", lambda: 5678)
    monkeypatch.setattr(
        host_runner,
        "container_path",
        lambda _path: Path("/workspace/logs/issue294/test_run"),
    )
    monkeypatch.setattr(
        host_runner,
        "checked",
        lambda command, *, cwd=None: commands.append(command),
    )

    host_runner._restore_host_ownership(output)

    assert commands == [
        [
            "docker",
            "exec",
            host_runner.CONTAINER,
            "chown",
            "-R",
            "1234:5678",
            "/workspace/logs/issue294/test_run",
        ]
    ]
