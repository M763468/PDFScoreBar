"""Subprocess execution with integrated logging."""

import logging
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def run_with_logging(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    log_level: int = logging.DEBUG,
) -> None:
    """
    Run a command and capture its stdout/stderr line-by-line,
    forwarding it to the Python logging system.
    """
    cmd_str = " ".join(cmd)
    logger.debug(f"Starting subprocess: {cmd_str}")

    with subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as p:
        if p.stdout:
            for line in p.stdout:
                line = line.rstrip("\n")
                logger.log(log_level, f"|> {line}")

        p.wait()
        if check and p.returncode != 0:
            logger.error(f"Subprocess failed with exit code {p.returncode}: {cmd_str}")
            raise subprocess.CalledProcessError(p.returncode, cmd)
