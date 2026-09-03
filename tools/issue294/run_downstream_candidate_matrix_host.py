#!/usr/bin/env python3
"""Run the Issue #294 historical/B/latest downstream candidate matrix from the host."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_same_original_ab_host as base
from tools.issue294 import run_same_original_ab_host_historical as historical

HOMR_URL = "https://github.com/liebharc/homr.git"
# Keep host-owned third-party checkouts out of logs/. Docker-created Issue #294
# outputs can leave that tree or its parents root-owned after interrupted runs.
# temp/ is repository-ignored and remains mount-visible at /workspace/temp.
HOMR_CACHE_ROOT = PROJECT_ROOT / "temp/issue294_upstream_homr"
B_COMMIT = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
ISSUE294_BRANCH = base.BRANCH
ISSUE294_BASE_COMMIT = base.BASE_COMMIT


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _validate_existing_summary(summary: Path, pages: list[str]) -> dict[str, Any]:
    payload = _load_json(summary)
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Existing same-original summary is incomplete: {summary}")
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError(f"Existing same-original summary has no pages: {summary}")

    actual_pages: list[str] = []
    for page in raw_pages:
        if not isinstance(page, dict) or not isinstance(page.get("image"), str):
            raise ValueError(f"Invalid page record in existing summary: {summary}")
        actual_pages.append(Path(str(page["image"])).stem.removeprefix("page_"))
    if actual_pages != pages:
        raise ValueError(
            "Existing same-original summary page mismatch: "
            f"requested={pages} existing={actual_pages} summary={summary}"
        )
    return payload


def _resolve_same_original_summary(
    run_tag: str,
    pages: list[str],
    checkout: dict[str, str],
) -> tuple[Path, bool]:
    """Reuse a completed A/B run or create it once when absent."""

    output_root = PROJECT_ROOT / "logs/issue294" / run_tag
    summary = output_root / "summary.json"
    if summary.is_file():
        _validate_existing_summary(summary, pages)
        # Reused runs still need the production container for the downstream matrix.
        base.require_container()
        return summary.resolve(), True

    if output_root.exists():
        raise RuntimeError(
            f"Issue #294 run directory exists without a completed summary: {output_root}. "
            "Use a new --run-tag or remove the incomplete run directory."
        )

    # The shared historical host adapter still contains an older exact-develop
    # assertion. The downstream matrix owns the invariant we actually need here:
    # clean Issue #294 branch, unchanged merge-base, and develop descending from
    # that fixed base. Reuse the already-validated source commit while the shared
    # A/B runner performs its remaining container checks.
    previous_require_host_checkout = base.require_host_checkout
    base.require_host_checkout = lambda: checkout["head"]
    try:
        ab = historical.run(run_tag, pages, None)
    finally:
        base.require_host_checkout = previous_require_host_checkout

    summary = Path(ab["summary"]).resolve()
    _validate_existing_summary(summary, pages)
    return summary, False


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


def _run_detector_preflight(label: str, source: Path, commit: str) -> dict[str, Any]:
    """Verify the exact detector-only import closure inside the production container first."""

    container_source = base.container_path(source)
    command = [
        "docker",
        "exec",
        "-w",
        str(base.CONTAINER_ROOT),
        "-e",
        f"PYTHONPATH={container_source}:{base.CONTAINER_ROOT}",
        base.CONTAINER,
        base.PIPELINE_PYTHON,
        "tools/issue294/run_latest_homr_detector_original.py",
        "--homr-source",
        str(container_source),
        "--homr-commit",
        commit,
        "--preflight-only",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} detector preflight failed ({completed.returncode}):\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"{label} detector preflight produced no JSON output")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{label} detector preflight returned invalid JSON: {lines[-1]!r}"
        ) from error
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise RuntimeError(f"{label} detector preflight incomplete: {payload!r}")
    optional = payload.get("optional_modules_imported")
    if optional != []:
        raise RuntimeError(f"{label} imported excluded optional HOMR modules: {optional!r}")
    if payload.get("homr_commit") != commit:
        raise RuntimeError(
            f"{label} detector preflight commit mismatch: expected={commit} "
            f"actual={payload.get('homr_commit')}"
        )
    return payload


def _prepare_matrix_output(matrix_root: Path) -> tuple[Path, bool]:
    """Reuse a completed matrix or discard only an incomplete generated matrix tree."""

    report = matrix_root / "report.json"
    if not matrix_root.exists():
        return report, False
    if report.is_file():
        payload = _load_json(report)
        if isinstance(payload, dict) and payload.get("status") == "completed":
            return report, True

    # The host wrapper's previous finally block restores ownership after a failed
    # docker invocation. Removing this generated subtree is safe and preserves the
    # completed same-original A/B summary and provenance in its parent run root.
    shutil.rmtree(matrix_root)
    return report, False


def run(run_tag: str, pages: list[str]) -> dict[str, str]:
    checkout = _require_issue294_checkout()
    summary, reused_same_original = _resolve_same_original_summary(run_tag, pages, checkout)
    output_root = PROJECT_ROOT / "logs/issue294" / run_tag

    latest_commit = _latest_main_commit()
    b_source = _prepare_homr_source(B_COMMIT)
    c_source = _prepare_homr_source(latest_commit)

    # Do this before deleting/re-running any generated matrix work. This catches
    # source/runtime import incompatibilities (such as optional PDF/OCR deps) at
    # the cheapest boundary and for both candidates before fixed support or CNN work.
    b_preflight = _run_detector_preflight("B_b377", b_source, B_COMMIT)
    c_preflight = _run_detector_preflight("C_latest", c_source, latest_commit)

    matrix_root = output_root / "downstream_candidate_matrix"
    report, reused_matrix = _prepare_matrix_output(matrix_root)

    if not reused_matrix:
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

    if not report.is_file():
        raise FileNotFoundError(report)
    payload = _load_json(report)
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete downstream matrix: {report}")

    provenance = {
        "schema_version": "issue294.downstream_candidate_matrix_host.v6",
        "run_tag": run_tag,
        "pages": pages,
        "checkout": checkout,
        "same_original_summary": str(summary.relative_to(PROJECT_ROOT)),
        "same_original_reused": reused_same_original,
        "downstream_matrix_reused": reused_matrix,
        "homr_cache_root": str(HOMR_CACHE_ROOT.relative_to(PROJECT_ROOT)),
        "B_source": str(b_source.relative_to(PROJECT_ROOT)),
        "B_commit": B_COMMIT,
        "B_detector_preflight": b_preflight,
        "upstream_discovery_ref": "refs/heads/main",
        "upstream_resolved_commit": latest_commit,
        "upstream_source": str(c_source.relative_to(PROJECT_ROOT)),
        "upstream_detector_preflight": c_preflight,
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
        "same_original_reused": str(reused_same_original).lower(),
        "matrix_report": str(report),
        "downstream_matrix_reused": str(reused_matrix).lower(),
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
