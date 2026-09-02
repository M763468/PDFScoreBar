#!/usr/bin/env python3
"""Run the Issue #294 A/B/latest downstream candidate matrix from the host."""

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


def _latest_main_commit() -> str:
    text = base.capture(["git", "ls-remote", HOMR_URL, "refs/heads/main"], cwd=PROJECT_ROOT)
    parts = text.split()
    if len(parts) != 2 or parts[1] != "refs/heads/main":
        raise RuntimeError(f"Unexpected HOMR ls-remote result: {text!r}")
    return parts[0]


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
    # Existing historical adapter owns all branch/container/base-image provenance checks.
    ab = historical.run(run_tag, pages, None)
    output_root = PROJECT_ROOT / "logs/issue294" / run_tag
    summary = Path(ab["summary"]).resolve()

    latest_commit = _latest_main_commit()
    homr_source = _prepare_homr_source(latest_commit)
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
        "--homr-source",
        str(base.container_path(homr_source)),
        "--homr-commit",
        latest_commit,
        "--output-root",
        str(base.container_path(matrix_root)),
    ]
    try:
        base.checked(command, cwd=PROJECT_ROOT)
    finally:
        base._restore_host_ownership(output_root)
        base._restore_host_ownership(homr_source)

    report = matrix_root / "report.json"
    if not report.is_file():
        raise FileNotFoundError(report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete downstream matrix: {report}")

    provenance = {
        "schema_version": "issue294.downstream_candidate_matrix_host.v1",
        "run_tag": run_tag,
        "pages": pages,
        "same_original_summary": str(summary.relative_to(PROJECT_ROOT)),
        "upstream_discovery_ref": "refs/heads/main",
        "upstream_resolved_commit": latest_commit,
        "upstream_source": str(homr_source.relative_to(PROJECT_ROOT)),
        "upstream_tracking_policy": (
            "discover floating main, resolve immutable commit, gate immutable candidate, "
            "never switch production to a floating ref"
        ),
        "matrix_report": str(report.relative_to(PROJECT_ROOT)),
        "gates": payload.get("gates"),
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
        "latest_homr_commit": latest_commit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
