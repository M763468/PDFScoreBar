#!/usr/bin/env python3
"""Run the Issue #294 same-original A/B gate from the WSL/Linux host."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "pdfscore_issue294_profile_worktree"
EXPECTED_IMAGE_ID = "sha256:5e1265263a5ba014814002c02fcfaf7f07a61e7000c13697db6c3087c7d2acdc"
BASE_COMMIT = "9df0be734dcb0b7fec14b56c8d1a8b20ec55af5d"
BRANCH = "perf/issue294-homr-baseline-refresh"
CONTAINER_ROOT = Path("/workspace")
PIPELINE_PYTHON = "/opt/venv_pipeline/bin/python"
PINNED_HOMR_PYTHON = "/opt/venv_stage_e_homr/bin/python"
SCORE = "Shostakovich-Sym5-Va"
ALLOWED_PAGES = {"012", "013", "014"}


def capture(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        command,
        cwd=cwd,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def checked(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def require_host_checkout() -> str:
    status = capture(["git", "status", "--porcelain"], cwd=PROJECT_ROOT)
    if status:
        raise RuntimeError("Issue #294 experiment requires a clean host checkout:\n" + status)
    branch = capture(["git", "branch", "--show-current"], cwd=PROJECT_ROOT)
    if branch != BRANCH:
        raise RuntimeError(f"Expected branch {BRANCH}, got {branch or '<detached>'}")
    head = capture(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT)
    merge_base = capture(["git", "merge-base", "HEAD", "develop"], cwd=PROJECT_ROOT)
    develop = capture(["git", "rev-parse", "develop"], cwd=PROJECT_ROOT)
    if develop != BASE_COMMIT:
        raise RuntimeError(f"Expected develop {BASE_COMMIT}, got {develop}")
    if merge_base != BASE_COMMIT:
        raise RuntimeError(f"Issue #294 branch is no longer based on {BASE_COMMIT}: {merge_base}")
    return head


def require_container() -> None:
    running = capture(["docker", "inspect", "--format", "{{.State.Running}}", CONTAINER])
    if running != "true":
        raise RuntimeError(f"Container {CONTAINER} is not running")
    image_id = capture(["docker", "inspect", "--format", "{{.Image}}", CONTAINER])
    if image_id != EXPECTED_IMAGE_ID:
        raise RuntimeError(f"Container {CONTAINER} uses {image_id}, expected {EXPECTED_IMAGE_ID}")
    workspace_source = capture(
        [
            "docker",
            "inspect",
            "--format",
            '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}',
            CONTAINER,
        ]
    )
    if not workspace_source:
        raise RuntimeError(f"Container {CONTAINER} has no /workspace mount")
    if Path(workspace_source).resolve() != PROJECT_ROOT.resolve():
        raise RuntimeError(
            f"Container /workspace is mounted from {workspace_source}, expected {PROJECT_ROOT}"
        )


def container_path(host_path: Path) -> Path:
    resolved = host_path.resolve()
    try:
        relative = resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        # This worktree shares logs/data via symlinks to the manager worktree.
        # The profiling container mounts that manager path at the same absolute
        # location, so preserve it for container-side access.
        return resolved
    return CONTAINER_ROOT / relative


def _restore_host_ownership(path: Path) -> None:
    """Return container-created experiment outputs to the invoking host user."""

    resolved = path.resolve()
    if not resolved.exists():
        return
    checked(
        [
            "docker",
            "exec",
            CONTAINER,
            "chown",
            "-R",
            f"{os.getuid()}:{os.getgid()}",
            str(container_path(resolved)),
        ],
        cwd=PROJECT_ROOT,
    )


def _run_comparator(summary: Path, comparison: Path) -> None:
    checked(
        [
            "docker",
            "exec",
            "-w",
            str(CONTAINER_ROOT),
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            PIPELINE_PYTHON,
            "tools/issue294/compare_same_original_ab.py",
            "--summary",
            str(container_path(summary)),
            "--output",
            str(container_path(comparison)),
        ],
        cwd=PROJECT_ROOT,
    )


def _run_pinned_runtime_probe(output: Path) -> dict[str, object]:
    checked(
        [
            "docker",
            "exec",
            "-w",
            str(CONTAINER_ROOT),
            CONTAINER,
            PINNED_HOMR_PYTHON,
            "tools/issue294/probe_pinned_homr_runtime.py",
            "--output",
            str(container_path(output)),
        ],
        cwd=PROJECT_ROOT,
    )
    if not output.is_file():
        raise FileNotFoundError(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete pinned runtime probe: {output}")
    return payload


def _run_fixed_support_replay(summary: Path, support_root: Path, replay_root: Path) -> None:
    checked(
        [
            "docker",
            "exec",
            "-w",
            str(CONTAINER_ROOT),
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            PIPELINE_PYTHON,
            "tools/issue294/replay_hybrid_with_fixed_support.py",
            "--summary",
            str(container_path(summary)),
            "--support-root",
            str(container_path(support_root)),
            "--output-root",
            str(container_path(replay_root)),
        ],
        cwd=PROJECT_ROOT,
    )


def run(run_tag: str, pages: list[str], support_root: Path | None = None) -> dict[str, str]:
    source_commit = require_host_checkout()
    require_container()
    invalid = [page for page in pages if page not in ALLOWED_PAGES]
    if invalid:
        raise ValueError(f"Unsupported representative pages: {invalid}")
    if not pages:
        raise ValueError("At least one page is required")
    if len(set(pages)) != len(pages):
        raise ValueError("Duplicate page requested")

    images = [
        PROJECT_ROOT / "data/evaluation2/images" / SCORE / f"page_{page}.png" for page in pages
    ]
    for image in images:
        if not image.is_file():
            raise FileNotFoundError(image)

    resolved_support_root: Path | None = None
    if support_root is not None:
        resolved_support_root = support_root.resolve()
        if not resolved_support_root.is_dir():
            raise FileNotFoundError(resolved_support_root)
        container_path(resolved_support_root)

    output_root = PROJECT_ROOT / "logs/issue294" / run_tag
    if output_root.exists():
        raise FileExistsError(output_root)
    container_output = container_path(output_root)

    command = [
        "docker",
        "exec",
        "-w",
        str(CONTAINER_ROOT),
        "-e",
        "PYTHONPATH=/workspace",
        CONTAINER,
        PIPELINE_PYTHON,
        "tools/issue294/run_same_original_ab.py",
    ]
    for image in images:
        command.extend(["--image", str(container_path(image))])
    command.extend(["--output-root", str(container_output)])
    checked(command, cwd=PROJECT_ROOT)

    summary = output_root / "summary.json"
    if not summary.is_file():
        _restore_host_ownership(output_root)
        raise FileNotFoundError(summary)

    comparison = output_root / "comparison.json"
    pinned_probe_path = output_root / "A_pinned_runtime_probe.json"
    replay_report: Path | None = None
    pinned_probe: dict[str, object]
    try:
        _run_comparator(summary, comparison)
        if not comparison.is_file():
            raise FileNotFoundError(comparison)

        pinned_probe = _run_pinned_runtime_probe(pinned_probe_path)

        if resolved_support_root is not None:
            replay_root = output_root / "fixed_support_replay"
            _run_fixed_support_replay(summary, resolved_support_root, replay_root)
            replay_report = replay_root / "report.json"
            if not replay_report.is_file():
                raise FileNotFoundError(replay_report)
    finally:
        # docker exec runs as root in the production container. Restore the
        # mounted run tree before any host-side write (and even on post-run
        # failures) so provenance and later cleanup remain user-writable.
        _restore_host_ownership(output_root)

    provenance = {
        "schema_version": "issue294.same_original_host_provenance.v1",
        "source_commit": source_commit,
        "branch": BRANCH,
        "develop": BASE_COMMIT,
        "container": CONTAINER,
        "image_id": EXPECTED_IMAGE_ID,
        "pages": pages,
        "summary": str(summary.relative_to(PROJECT_ROOT)),
        "comparison": str(comparison.relative_to(PROJECT_ROOT)),
        "pinned_runtime_probe": str(pinned_probe_path.relative_to(PROJECT_ROOT)),
        "pinned_runtime_hard_contract": pinned_probe.get("hard_contract_pass"),
        "host_output_owner": {"uid": os.getuid(), "gid": os.getgid()},
        "fixed_support_root": (
            str(resolved_support_root.relative_to(PROJECT_ROOT))
            if resolved_support_root is not None
            else None
        ),
        "fixed_support_replay": (
            str(replay_report.relative_to(PROJECT_ROOT)) if replay_report is not None else None
        ),
    }
    provenance_path = output_root / "host_provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if pinned_probe.get("hard_contract_pass") is not True:
        raise RuntimeError(f"Pinned Stage-E runtime provenance gate failed: {pinned_probe_path}")

    result = {
        "summary": str(summary),
        "comparison": str(comparison),
        "pinned_runtime_probe": str(pinned_probe_path),
        "provenance": str(provenance_path),
    }
    if replay_report is not None:
        result["fixed_support_replay"] = str(replay_report)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--page",
        action="append",
        choices=sorted(ALLOWED_PAGES),
        dest="pages",
        help="Representative page number. Repeat for multiple pages. Defaults to page 013.",
    )
    parser.add_argument(
        "--support-root",
        type=Path,
        help=(
            "Optional retained production current_support root. When supplied, replay A/B "
            "against the exact same current-x4 HOMR and OMR-DLN support artifacts."
        ),
    )
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.pages or ["013"], args.support_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
