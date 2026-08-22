"""Run the standard Issue #283 replay with the grayscale-reuse worker shim."""

from __future__ import annotations

import subprocess

from tools.issue283 import run_current_homr_replay

_ORIGINAL_POPEN = subprocess.Popen
_WORKER_MODULE = "src.pipeline.detection.current_homr_worker"
_EXPERIMENT_MODULE = "tools.issue283.current_homr_worker_gray_reuse"


def _experiment_popen(command, *args, **kwargs):
    patched = list(command)
    try:
        index = patched.index(_WORKER_MODULE)
    except ValueError:
        pass
    else:
        patched[index] = _EXPERIMENT_MODULE
    return _ORIGINAL_POPEN(patched, *args, **kwargs)


def main() -> int:
    run_current_homr_replay.subprocess.Popen = _experiment_popen
    try:
        return run_current_homr_replay.main()
    finally:
        run_current_homr_replay.subprocess.Popen = _ORIGINAL_POPEN


if __name__ == "__main__":
    raise SystemExit(main())
