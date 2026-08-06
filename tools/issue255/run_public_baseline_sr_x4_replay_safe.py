#!/usr/bin/env python3
"""Run the Issue #255 SR x4 replay with a container-local Git safety override."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tools.issue255 import run_public_baseline_sr_x4_replay as replay

_SAFE_DIRECTORY_ENV = (
    "-e",
    "GIT_CONFIG_COUNT=1",
    "-e",
    "GIT_CONFIG_KEY_0=safe.directory",
    "-e",
    "GIT_CONFIG_VALUE_0=/workspace",
)


def _with_safe_directory(command: Sequence[str]) -> tuple[str, ...]:
    """Add a process-local safe.directory only to the container HEAD check."""

    parts = tuple(command)
    prefix = ("docker", "exec", "-w", "/workspace")
    suffix = ("git", "rev-parse", "HEAD")
    if parts[: len(prefix)] == prefix and parts[-len(suffix) :] == suffix:
        return (*prefix, *_SAFE_DIRECTORY_ENV, *parts[len(prefix) :])
    return parts


def _safe_run(command: Sequence[str], **kwargs: Any) -> Any:
    return _ORIGINAL_RUN(_with_safe_directory(command), **kwargs)


_ORIGINAL_RUN = replay._run


def main() -> int:
    replay._run = _safe_run
    return replay.main()


if __name__ == "__main__":
    raise SystemExit(main())
