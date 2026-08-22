"""Validate x4 grayscale decode reuse against retained Issue #281 artifacts."""

from __future__ import annotations

import subprocess

from tools.issue283 import validate_vectorized_thin_barline

_ORIGINAL_RUN = subprocess.run
_BASE_RUNNER = "tools/issue283/run_current_homr_replay.py"
_EXPERIMENT_RUNNER = "tools/issue283/run_gray_reuse_replay.py"


def _experiment_run(command, *args, **kwargs):
    patched = list(command)
    try:
        index = patched.index(_BASE_RUNNER)
    except ValueError:
        pass
    else:
        patched[index] = _EXPERIMENT_RUNNER
    return _ORIGINAL_RUN(patched, *args, **kwargs)


def main() -> int:
    validate_vectorized_thin_barline.subprocess.run = _experiment_run
    try:
        return validate_vectorized_thin_barline.main()
    finally:
        validate_vectorized_thin_barline.subprocess.run = _ORIGINAL_RUN


if __name__ == "__main__":
    raise SystemExit(main())
