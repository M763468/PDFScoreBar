#!/usr/bin/env python3
"""Run fresh Issue #294 full68 with current develop and mapping-guarded grouping.

The wrapper intentionally leaves production code/config untouched. It reuses the
existing full68 A/B/C host harness, but:

* requires the merged #277 production commit to be an ancestor of the execution HEAD;
* replaces the stale pre-#277 checkout guard with provenance-only ancestry checks; and
* routes downstream numbering through the experiment-only mapping-guarded grouping
  entrypoint.

The full68 runner's historical A-equality gates remain diagnostics. Completion of
68/68 pages is the execution gate here; semantic/MMR acceptance is performed by
``run_post277_mapping_guarded_mmr.py`` against the accepted #264 physical-GT contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_downstream_candidate_matrix_full68_host as full68_host
from tools.issue294 import run_downstream_candidate_matrix_host as matrix_host
from tools.issue294 import run_same_original_ab_host as base

REQUIRED_DEVELOP_COMMIT = "edc17ee08de6694827c67d4ab8b30c2adc1f05e3"
DEFAULT_LATEST_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"
STANDARD_MATRIX_SCRIPT = "tools/issue294/run_downstream_candidate_matrix.py"
MAPPING_GUARDED_MATRIX_SCRIPT = (
    "tools/issue294/run_downstream_candidate_matrix_mapping_guarded.py"
)


def _capture(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def _require_ancestor(ancestor: str, descendant: str) -> None:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Required commit {ancestor} is not an ancestor of execution HEAD {descendant}. "
            "Merge current develop into the Issue #294 branch before running this gate."
        )


def require_post277_checkout() -> dict[str, str]:
    head = _capture(["git", "rev-parse", "HEAD"])
    branch = _capture(["git", "branch", "--show-current"])
    _require_ancestor(base.BASE_COMMIT, head)
    _require_ancestor(REQUIRED_DEVELOP_COMMIT, head)
    return {
        "branch": branch or "<detached>",
        "head": head,
        "base_commit": base.BASE_COMMIT,
        "develop_head": REQUIRED_DEVELOP_COMMIT,
        "required_develop_ancestor": REQUIRED_DEVELOP_COMMIT,
    }


def rewrite_matrix_command(command: list[str]) -> list[str]:
    rewritten = list(command)
    for index, value in enumerate(rewritten):
        if value == STANDARD_MATRIX_SCRIPT:
            rewritten[index] = MAPPING_GUARDED_MATRIX_SCRIPT
    return rewritten


def run(*, run_tag: str, latest_commit: str, chunk_size: int) -> dict[str, Any]:
    checkout = require_post277_checkout()
    original_checkout = matrix_host._require_issue294_checkout
    original_checked = base.checked

    def checked(command: list[str], *, cwd: Path | None = None) -> None:
        return original_checked(rewrite_matrix_command(command), cwd=cwd)

    matrix_host._require_issue294_checkout = require_post277_checkout
    base.checked = checked
    try:
        preflight = matrix_host.run_preflight(latest_commit)
        payload = full68_host.run(
            run_tag=run_tag,
            latest_commit=latest_commit,
            chunk_size=chunk_size,
        )
    finally:
        matrix_host._require_issue294_checkout = original_checkout
        base.checked = original_checked

    if payload.get("status") != "completed" or int(payload.get("completed_page_count", 0)) != 68:
        raise RuntimeError(
            "Post-#277 mapping-guarded full68 did not complete 68/68 pages: "
            f"status={payload.get('status')} pages={payload.get('completed_page_count')}"
        )

    root = PROJECT_ROOT / "logs/issue294" / run_tag
    wrapper_report = root / "post277_mapping_guarded_full68_host.json"
    report = {
        "schema_version": "issue294.post277_mapping_guarded_full68_host.v1",
        "status": "completed",
        "run_tag": run_tag,
        "checkout": checkout,
        "required_develop_commit": REQUIRED_DEVELOP_COMMIT,
        "latest_homr_commit": latest_commit,
        "mapping_guarded_grouping": True,
        "production_source_modified": False,
        "production_dispatch_modified": False,
        "matrix_entrypoint": MAPPING_GUARDED_MATRIX_SCRIPT,
        "detector_preflight": preflight,
        "full68_manifest": str((root / "full68_host.json").resolve()),
        "completed_page_count": int(payload["completed_page_count"]),
        "historical_A_comparison_gates_diagnostic_only": payload.get("gates"),
    }
    wrapper_report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default="issue294_post277_full68_01")
    parser.add_argument("--latest-homr-commit", default=DEFAULT_LATEST_COMMIT)
    parser.add_argument("--chunk-size", type=int, default=6)
    args = parser.parse_args()
    try:
        payload = run(
            run_tag=args.run_tag,
            latest_commit=args.latest_homr_commit,
            chunk_size=args.chunk_size,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
