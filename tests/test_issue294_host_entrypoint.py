from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issue294_complete_host_gate_bootstraps_repo_imports(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "tools/issue294/run_same_original_gate_host.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--run-tag" in completed.stdout
    assert "--page" in completed.stdout
