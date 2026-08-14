#!/usr/bin/env python3
"""Container entrypoint for the Issue #264 Phase C regression runner.

The maintained pipeline image intentionally does not require the Git CLI.  The host
validation wrapper therefore passes the exact repository HEAD through
``ISSUE264_HOST_GIT_HEAD``.  Keep the underlying runner usable outside Docker, where
its normal ``git rev-parse HEAD`` fallback remains valid.
"""

from __future__ import annotations

import os

from tools.issue264 import run_phase_c_mmr_regression as runner


def main() -> int:
    host_git_head = os.environ.get("ISSUE264_HOST_GIT_HEAD")
    if host_git_head:
        runner.git_head = lambda: host_git_head
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
