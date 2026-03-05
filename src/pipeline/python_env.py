"""Python interpreter selection for pipeline sub-processes."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def is_in_container() -> bool:
    """Checks if the current process is running inside a Docker container."""
    # Common markers for being inside one of our project containers
    return Path("/.dockerenv").exists() or (
        Path("/workspace").exists() and Path("/opt/venv_sr").exists()
    )


def get_docker_exec_prefix() -> List[str]:
    """Returns the docker exec prefix if sr_eval_gpu is running and we are on host."""
    if is_in_container():
        return []

    try:
        # Check if sr_eval_gpu is running
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=sr_eval_gpu",
                "--filter",
                "status=running",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and "sr_eval_gpu" in result.stdout:
            # We set PYTHONPATH to /workspace which is where the volume is mounted inside the container
            return [
                "docker",
                "exec",
                "-w",
                "/workspace",
                "-e",
                "PYTHONPATH=/workspace:/workspace/external/homr",
                "sr_eval_gpu",
            ]
    except FileNotFoundError:
        logger.debug("docker command not found, cannot use docker exec prefix.")
    except Exception as e:
        logger.warning(f"Error checking for docker container: {e}")
    return []


def get_pipeline_python(step_name: Optional[str] = None) -> List[str]:
    """Returns the appropriate Python interpreter command (possibly with docker exec).

    Args:
        step_name: Optional step name (e.g., 'detection', 'homr', 'omr_dln', 'sr', 'pdf_to_images', 'numbering')

    Order of preference:
    1. PIPELINE_PYTHON environment variable (explicit override).
    2. For heavy steps (detection/homr/omr_dln/sr):
       a. If in container: /opt/venv_sr/bin/python.
       b. If on host and sr_eval_gpu is running: 'docker exec sr_eval_gpu /opt/venv_sr/bin/python'.
    3. For pdf_to_images: Fallback to .venv_pdf/bin/python.
    4. Fallback to current sys.executable.
    """
    env_python = os.environ.get("PIPELINE_PYTHON")

    # 1. Check for heavy steps first
    if step_name in ("detection", "homr", "omr_dln", "sr"):
        if is_in_container():
            if Path("/opt/venv_sr/bin/python").exists():
                return ["/opt/venv_sr/bin/python"]
        else:
            prefix = get_docker_exec_prefix()
            if prefix:
                logger.info(f"Using {prefix} for step '{step_name}'")
                return prefix + ["/opt/venv_sr/bin/python"]

    # 2. Explicit override
    if env_python:
        return [env_python]
    # 3. If already in container but not a heavy step (or /opt/venv_sr missing)
    if is_in_container():
        return [sys.executable]

    # 4. Default host fallback for specific steps
    if step_name == "pdf_to_images":
        venv_pdf_python = PROJECT_ROOT / ".venv_pdf/bin/python"
        if venv_pdf_python.exists():
            return [str(venv_pdf_python)]

    # 5. General fallback
    return [sys.executable]
