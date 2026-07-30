"""Subprocess execution with integrated logging."""

import logging
import subprocess
from collections import deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def run_with_logging(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    log_level: int = logging.DEBUG,
    failure_tail_lines: int = 80,
) -> None:
    """
    Run a command and capture its stdout/stderr line-by-line.

    Successful output is forwarded at ``log_level``. If the subprocess fails, the
    retained output tail is repeated at ERROR so callers that suppress DEBUG logs still
    receive the actionable child-process exception.
    """
    cmd_str = " ".join(cmd)
    logger.debug(f"Starting subprocess: {cmd_str}")
    output_tail: deque[str] = deque(maxlen=max(1, failure_tail_lines))

    with subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        if process.stdout:
            for line in process.stdout:
                line = line.rstrip("\n")
                output_tail.append(line)
                logger.log(log_level, f"|> {line}")

        process.wait()
        if check and process.returncode != 0:
            logger.error(f"Subprocess failed with exit code {process.returncode}: {cmd_str}")
            if output_tail:
                logger.error("Subprocess output tail follows:")
                for line in output_tail:
                    logger.error(f"|> {line}")
            raise subprocess.CalledProcessError(
                process.returncode,
                cmd,
                output="\n".join(output_tail),
            )
