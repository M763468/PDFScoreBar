#!/usr/bin/env python3
"""Container entrypoint for the Issue #277 targeted full68 MMR runner.

The profiling image intentionally does not contain git.  This wrapper requires
an explicit host-worktree commit through ``ISSUE277_GIT_HEAD`` and injects that
value into the experiment-only full68 report without weakening provenance.
"""

from __future__ import annotations

import os
import re

from tools.issue277 import run_targeted_mmr_full68 as target

_SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def resolve_host_git_head(value: str | None) -> str:
    if value is None or not _SHA1_RE.fullmatch(value.strip()):
        raise RuntimeError(
            "ISSUE277_GIT_HEAD must be the 40-hex HEAD from the host Issue #277 worktree"
        )
    return value.strip().lower()


def main() -> int:
    git_head = resolve_host_git_head(os.environ.get("ISSUE277_GIT_HEAD"))
    target._git_head = lambda: git_head
    return target.main()


if __name__ == "__main__":
    raise SystemExit(main())
