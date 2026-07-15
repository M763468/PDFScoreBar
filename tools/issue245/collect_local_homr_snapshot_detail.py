#!/usr/bin/env python3
"""Collect exact dirty-tree provenance for the surviving local HOMR clone."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar/external/homr")
DEFAULT_OUTPUT = Path(
    "/home/masaki_muramatsu/ws_PDFScoreBar/logs/"
    "issue245_local_homr_snapshot_detail/local_homr_snapshot_detail.json"
)
SOURCE_PATHS = (
    "homr/autocrop.py",
    "homr/segmentation/config.py",
    "homr/segmentation/inference_segnet.py",
    "homr/main.py",
    "pyproject.toml",
)
MODEL_DIRS = (
    "homr/segmentation",
    "homr/transformer",
)
MODEL_SUFFIXES = {".onnx", ".pth", ".pt", ".zip"}
REFERENCE_PATTERN = re.compile(
    r"segnet|onnx|checkpoint|weight|model_url|download_url|version",
    re.IGNORECASE,
)
UNREACHABLE_PATTERN = re.compile(r"^(?:unreachable|dangling) commit ([0-9a-f]{40})$")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args])


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_lines(content: str, *, limit: int = 120) -> list[str]:
    return [
        line.strip()
        for line in content.splitlines()
        if REFERENCE_PATTERN.search(line)
    ][:limit]


def parse_unreachable_commits(output: str) -> list[str]:
    commits: list[str] = []
    for line in output.splitlines():
        match = UNREACHABLE_PATTERN.match(line.strip())
        if match:
            commits.append(match.group(1))
    return sorted(set(commits))


def git_text(repo: Path, *args: str) -> str | None:
    result = git(repo, *args)
    return result.stdout if result.returncode == 0 else None


def file_record(repo: Path, relative_path: str) -> dict[str, Any]:
    path = repo / relative_path
    record: dict[str, Any] = {
        "path": relative_path,
        "exists": path.is_file(),
    }
    if path.is_file():
        stat = path.stat()
        content = path.read_bytes()
        record.update(
            {
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .isoformat(),
                "sha256": sha256_bytes(content),
            }
        )
        try:
            record["reference_lines"] = reference_lines(content.decode("utf-8"))
        except UnicodeDecodeError:
            record["reference_lines"] = []

    head = git(repo, "show", f"HEAD:{relative_path}")
    record["exists_at_head"] = head.returncode == 0
    if head.returncode == 0:
        head_bytes = head.stdout.encode("utf-8")
        record["head_sha256"] = sha256_bytes(head_bytes)
        record["differs_from_head"] = record.get("sha256") != record["head_sha256"]
    return record


def commit_record(repo: Path, sha: str) -> dict[str, Any]:
    metadata = git(
        repo,
        "show",
        "-s",
        "--format=%H%x1f%cI%x1f%s",
        sha,
    )
    record: dict[str, Any] = {"commit": sha}
    if metadata.returncode == 0:
        parts = metadata.stdout.strip().split("\x1f", maxsplit=2)
        if len(parts) == 3:
            record.update(
                {
                    "committed_at": parts[1],
                    "subject": parts[2],
                }
            )
    snapshots: list[dict[str, Any]] = []
    for relative_path in SOURCE_PATHS:
        result = git(repo, "show", f"{sha}:{relative_path}")
        if result.returncode != 0:
            snapshots.append({"path": relative_path, "exists": False})
            continue
        content = result.stdout
        snapshots.append(
            {
                "path": relative_path,
                "exists": True,
                "sha256": sha256_bytes(content.encode("utf-8")),
                "reference_lines": reference_lines(content),
            }
        )
    record["source_snapshot"] = snapshots
    return record


def model_records(repo: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative_dir in MODEL_DIRS:
        root = repo / relative_dir
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in MODEL_SUFFIXES:
                continue
            stat = path.stat()
            records.append(
                {
                    "path": str(path.relative_to(repo)),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime)
                    .astimezone()
                    .isoformat(),
                    "sha256": sha256_file(path),
                }
            )
    return records


def venv_record(repo: Path) -> dict[str, Any]:
    python = repo / ".venv/bin/python"
    record: dict[str, Any] = {"python_path": str(python), "exists": python.is_file()}
    if not python.is_file():
        return record
    probe = run(
        [
            str(python),
            "-c",
            (
                "import json,sys; out={'python':sys.version}; "
                "\nfor name in ('homr','onnxruntime','numpy','cv2'):\n"
                " try:\n"
                "  mod=__import__(name); out[name]={'file':getattr(mod,'__file__',None),"
                "'version':getattr(mod,'__version__',None)}\n"
                " except Exception as exc:\n"
                "  out[name]={'error':repr(exc)}\n"
                "print(json.dumps(out))"
            ),
        ],
        cwd=repo,
    )
    record["returncode"] = probe.returncode
    record["stderr"] = probe.stderr.strip() or None
    if probe.returncode == 0:
        try:
            record["packages"] = json.loads(probe.stdout)
        except json.JSONDecodeError:
            record["stdout"] = probe.stdout
    else:
        record["stdout"] = probe.stdout
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if git(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        raise RuntimeError(f"not a Git worktree: {repo}")

    fsck = git(repo, "fsck", "--full", "--unreachable", "--no-reflogs")
    unreachable = parse_unreachable_commits(fsck.stdout)
    diff = git(repo, "diff", "--no-ext-diff", "--binary", "--")

    report = {
        "schema_version": "issue245.local_homr_snapshot_detail.v1",
        "status": "completed",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "repository": str(repo),
        "head": (git_text(repo, "rev-parse", "HEAD") or "").strip(),
        "branch": (git_text(repo, "branch", "--show-current") or "").strip(),
        "status_porcelain": (git_text(repo, "status", "--short", "--branch") or "").strip(),
        "diff_name_status": (git_text(repo, "diff", "--name-status", "--") or "").strip(),
        "diff_stat": (git_text(repo, "diff", "--stat", "--") or "").strip(),
        "diff": diff.stdout,
        "diff_sha256": sha256_bytes(diff.stdout.encode("utf-8")),
        "working_tree_files": [file_record(repo, path) for path in SOURCE_PATHS],
        "unreachable_commits": [commit_record(repo, sha) for sha in unreachable],
        "model_artifacts": model_records(repo),
        "local_venv": venv_record(repo),
        "limitations": [
            "The repository is inspected read-only; no checkout, reset, clean, fetch, or package installation is performed.",
            "Only the listed source files and HOMR segmentation/transformer model directories are captured.",
            "This snapshot is provenance evidence and is not yet selected as a production dependency.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Changed files: {report['diff_name_status'].count(chr(10)) + bool(report['diff_name_status'])}")
    print(f"Unreachable commits: {len(unreachable)}")
    print(f"HOMR model artifacts: {len(report['model_artifacts'])}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
