"""Isolated current-HOMR invocation used by the Issue #264 full-68 replay."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(request_path: Path, result_path: Path) -> Path:
    command = [
        sys.executable,
        "-m",
        "src.pipeline.detection.current_homr_worker",
        "--request",
        str(request_path),
        "--result",
        str(result_path),
    ]
    subprocess.run(command, check=True)
    if not result_path.is_file():
        raise FileNotFoundError(result_path)
    return result_path
