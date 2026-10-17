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
    """Checks if the current process is running inside a project Docker container."""
    return Path("/.dockerenv").exists() or (
        Path("/workspace").exists() and Path("/opt/venv_pipeline").exists()
    )


def get_docker_exec_prefix() -> List[str]:
    """Returns the canonical pipeline docker exec prefix when available from the host."""
    if is_in_container():
        return []

    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=pdfscore_pipeline_gpu",
                "--filter",
                "status=running",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and "pdfscore_pipeline_gpu" in result.stdout:
            return [
                "docker",
                "exec",
                "-w",
                "/workspace",
                "-e",
                "PYTHONPATH=/workspace",
                "pdfscore_pipeline_gpu",
            ]
    except FileNotFoundError:
        logger.debug("docker command not found, cannot use docker exec prefix.")
    except Exception as e:
        logger.warning(f"Error checking for docker container: {e}")
    return []


def get_pipeline_python(step_name: Optional[str] = None) -> List[str]:
    """Returns the appropriate Python interpreter command (possibly with docker exec).

    Args:
        step_name: Optional step name (e.g., 'detection', 'homr', 'omr_dln', 'sr',
            'pdf_to_images', 'numbering').

    Order of preference:
    1. For heavy steps (detection/homr/omr_dln/sr):
       a. If in the maintained container: /opt/venv_pipeline/bin/python.
       b. If on the host and the maintained container is running:
          docker exec pdfscore_pipeline_gpu /opt/venv_pipeline/bin/python.
    2. PIPELINE_PYTHON environment variable (explicit override when no maintained heavy-step
       environment was selected).
    3. For pdf_to_images: fallback to .venv_pdf/bin/python.
    4. Fallback to current sys.executable.
    """
    env_python = os.environ.get("PIPELINE_PYTHON")

    if step_name in ("detection", "homr", "omr_dln", "sr"):
        if is_in_container():
            if Path("/opt/venv_pipeline/bin/python").exists():
                return ["/opt/venv_pipeline/bin/python"]
        else:
            prefix = get_docker_exec_prefix()
            if prefix:
                logger.info(f"Using {prefix} for step '{step_name}'")
                return prefix + ["/opt/venv_pipeline/bin/python"]

    if env_python:
        return [env_python]

    if is_in_container():
        if Path("/opt/venv_pipeline/bin/python").exists():
            return ["/opt/venv_pipeline/bin/python"]
        return [sys.executable]

    if step_name == "pdf_to_images":
        venv_pdf_python = PROJECT_ROOT / ".venv_pdf/bin/python"
        if venv_pdf_python.exists():
            return [str(venv_pdf_python)]

    return [sys.executable]
