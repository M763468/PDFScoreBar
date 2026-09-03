#!/usr/bin/env python3
"""Run the Issue #294 historical/B/latest downstream candidate matrix from the host."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_same_original_ab_host as base
from tools.issue294 import run_same_original_ab_host_historical as historical

HOMR_URL = "https://github.com/liebharc/homr.git"
HOMR_CACHE_ROOT = PROJECT_ROOT / "logs/issue294/_upstream_homr"
B_COMMIT = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
ISSUE294_BRANCH = base.BRANCH
ISSUE294_BASE_COMMIT = base.BASE_COMMIT


def _latest_main_commit() -> str:
    text = base.capture(["git", "ls-remote", HOMR_URL, "refs/heads/main"], cwd=PROJECT_ROOT)
    parts = text.split()
    if len(parts) != 2 or parts[1] != "refs/heads/main":
        raise RuntimeError(f"Unexpected HOMR ls-remote result: {text!r}")
    return parts[0]


def _require_issue294_checkout() -> dict[str, str]:
    """Validate the fixed Issue #294 branch base without freezing local develop HEAD."""

    status = base.capture(["git", "status", "--porcelain"], cwd=PROJECT_ROOT)
    if status:
        raise RuntimeError("Issue #294 experiment requires a clean host checkout:\n" + status)

    branch = base.capture(["git", "branch", "--show-current"], cwd=PROJECT_ROOT)
    if branch != ISSUE294_BRANCH:
        raise RuntimeError(
            f"Expected branch {ISSUE294_BRANCH}, got {branch or '<detached>'}. "
            f"Run: git switch {ISSUE294_BRANCH}"
        )

    head = base.capture(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT)
    develop = base.capture(["git", "rev-parse", "develop"], cwd=PROJECT_ROOT)
    base_in_develop = base.capture(
        ["git", "merge-base", ISSUE294_BASE_COMMIT, "develop"], cwd=PROJECT_ROOT
    )
    if base_in_develop != ISSUE294_BASE_COMMIT:
        raise RuntimeError(
            "Current develop no longer contains the fixed Issue #294 base: "
            f"base={ISSUE294_BASE_COMMIT} develop={develop} merge_base={base_in_develop}"
        )

    branch_merge_base = base.capture(["git", "merge-base", "HEAD", "develop"], cwd=PROJECT_ROOT)
    if branch_merge_base != ISSUE294_BASE_COMMIT:
        raise RuntimeError(
            "Issue #294 branch base changed unexpectedly: "
            f"expected={ISSUE294_BASE_COMMIT} actual={branch_merge_base}"
        )

    return {
        "branch": branch,
        "head": head,
        "base_commit": ISSUE294_BASE_COMMIT,
        "develop_head": develop,
    }


def _prepare_homr_source(commit: str) -> Path:
    source = HOMR_CACHE_ROOT / commit
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", HOMR_URL, str(source)],
            cwd=PROJECT_ROOT,
            check=True,
        )
        subprocess.run(["git", "-C", str(source), "fetch", "origin", commit], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", commit], check=True)
    actual = base.capture(["git", "-C", str(source), "rev-parse", "HEAD"])
    if actual != commit:
        raise RuntimeError(f"HOMR cache mismatch: expected={commit} actual={actual}")
    return source


def run(run_tag: str, pages: list[str]) -> dict[str, str]:
    checkout = _require_issue294_checkout()

    # The shared historical host adapter still contains an older exact-develop
    # assertion. The downstream matrix owns the stricter invariant we actually
    # need here: clean Issue #294 branch, unchanged merge-base, and a develop
    # ref that still descends from that fixed base. Reuse the validated source
    # commit while the shared A/B runner performs its remaining container checks.
    previous_require_host_checkout = base.require_host_checkout
    base.require_host_checkout = lambda: checkout["head"]
    try:
        ab = historical.run(run_tag, pages, None)
    finally:
        base.require_host_checkout = previous_require_host_checkout

    output_root = PROJECT_ROOT / "logs/issue294" / run_tag
    summary = Path(ab["summary"]).resolve()

    latest_commit = _latest_main_commit()
    b_source = _prepare_homr_source(B_COMMIT)
    c_source = _prepare_homr_source(latest_commit)
    matrix_root = output_root / "downstream_candidate_matrix"
    command = [
        "docker",
        "exec",
        "-w",
        str(base.CONTAINER_ROOT),
        "-e",
        "PYTHONPATH=/workspace",
        base.CONTAINER,
        base.PIPELINE_PYTHON,
        "tools/issue294/run_downstream_candidate_matrix.py",
        "--summary",
        str(base.container_path(summary)),
        "--b-homr-source",
        str(base.container_path(b_source)),
        "--b-homr-commit",
        B_COMMIT,
        "--c-homr-source",
        str(base.container_path(c_source)),
        "--c-homr-commit",
        latest_commit,
        "--output-root",
        str(base.container_path(matrix_root)),
    ]
    try:
        base.checked(command, cwd=PROJECT_ROOT)
    finally:
        base._restore_host_ownership(output_root)
        base._restore_host_ownership(b_source)
        if c_source != b_source:
            base._restore_host_ownership(c_source)

    report = matrix_root / "report.json"
    if not report.is_file():
        raise FileNotFoundError(report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete downstream matrix: {report}")

    provenance = {
        "schema_version": "issue294.downstream_candidate_matrix_host.v3",
        "run_tag": run_tag,
        "pages": pages,
        "checkout": checkout,
        "same_original_summary": str(summary.relative_to(PROJECT_ROOT)),
        "B_source": str(b_source.relative_to(PROJECT_ROOT)),
        "B_commit": B_COMMIT,
        "upstream_discovery_ref": "refs/heads/main",
        "upstream_resolved_commit": latest_commit,
        "upstream_source": str(c_source.relative_to(PROJECT_ROOT)),
        "upstream_tracking_policy": (
            "discover floating main, resolve immutable commit, gate immutable candidate, "
            "never switch production to a floating ref"
        ),
        "matrix_report": str(report.relative_to(PROJECT_ROOT)),
        "gates": payload.get("gates"),
        "diagnostics": payload.get("diagnostics"),
    }
    provenance_path = output_root / "downstream_candidate_matrix_host.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "summary": str(summary),
        "matrix_report": str(report),
        "provenance": str(provenance_path),
        "B_homr_commit": B_COMMIT,
        "latest_homr_commit": latest_commit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"Required checkout: git switch {ISSUE294_BRANCH}",
    )
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--page",
        action="append",
        choices=sorted(base.ALLOWED_PAGES),
        dest="pages",
        help="Representative page. Repeat for multiple pages; defaults to 013.",
    )
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.pages or ["013"])
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
