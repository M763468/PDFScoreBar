#!/usr/bin/env python3
"""Run the Issue #294 same-original A/B gate from the WSL/Linux host."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "pdfscore_issue293_profile"
EXPECTED_IMAGE_ID = "sha256:5e1265263a5ba014814002c02fcfaf7f07a61e7000c13697db6c3087c7d2acdc"
BASE_COMMIT = "9df0be734dcb0b7fec14b56c8d1a8b20ec55af5d"
BRANCH = "perf/issue294-homr-baseline-refresh"
CONTAINER_ROOT = Path("/workspace")
PIPELINE_PYTHON = "/opt/venv_pipeline/bin/python"
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
    running = capture(
        ["docker", "inspect", "--format", "{{.State.Running}}", CONTAINER]
    )
    if running != "true":
        raise RuntimeError(f"Container {CONTAINER} is not running")
    image_id = capture(["docker", "inspect", "--format", "{{.Image}}", CONTAINER])
    if image_id != EXPECTED_IMAGE_ID:
        raise RuntimeError(
            f"Container {CONTAINER} uses {image_id}, expected {EXPECTED_IMAGE_ID}"
        )
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
    relative = host_path.resolve().relative_to(PROJECT_ROOT.resolve())
    return CONTAINER_ROOT / relative


def run(run_tag: str, pages: list[str]) -> dict[str, str]:
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
        raise FileNotFoundError(summary)
    comparison = output_root / "comparison.json"
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
    if not comparison.is_file():
        raise FileNotFoundError(comparison)

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
    }
    provenance_path = output_root / "host_provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "summary": str(summary),
        "comparison": str(comparison),
        "provenance": str(provenance_path),
    }


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
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.pages or ["013"])
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
