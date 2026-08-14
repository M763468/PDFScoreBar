#!/usr/bin/env python3
"""Container entrypoint for the Issue #264 Phase C regression runner.

The host wrapper supplies the Git HEAD because the maintained pipeline image does
not require Git.  Before running Phase C, this entrypoint also installs the
production-equivalent Phase-A semantic-support replay: current HOMR is rerun on the
retained canonical x4 SR images, while detector inference/SR/OMR-DLN stay frozen.
"""

from __future__ import annotations

import os

from tools.issue264 import run_phase_c_mmr_regression as runner
from tools.issue264.phase_c_phase_a_support import (
    augment_report,
    install_phase_a_support_replay,
)


def main() -> int:
    host_git_head = os.environ.get("ISSUE264_HOST_GIT_HEAD")
    if host_git_head:
        runner.git_head = lambda: host_git_head

    args = runner.parse_args()
    run_dir = args.output_root / args.run_id
    support_provenance = install_phase_a_support_replay(
        runner,
        run_dir=run_dir,
        resume=args.resume,
    )
    report_path = runner.run(run_dir, resume=args.resume)
    augment_report(report_path, support_provenance=support_provenance)
    report = runner.load_json(report_path)
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
