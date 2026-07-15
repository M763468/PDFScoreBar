#!/usr/bin/env python3
"""Collect non-destructive local HOMR Git and model provenance for Issue #245."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_OUTPUT_REL = Path(
    "logs/issue245_local_homr_provenance/local_homr_provenance.json"
)
DEFAULT_AFTER = "2025-12-15T00:00:00+09:00"
DEFAULT_BEFORE = "2026-02-15T23:59:59+09:00"
MODEL_SUFFIXES = {".onnx", ".zip", ".pt", ".pth"}
SOURCE_PATHS = (
    "homr/segmentation/config.py",
    "homr/segmentation/segnet.py",
    "homr/main.py",
)
REFERENCE_PATTERN = re.compile(
    r"segnet|onnx|checkpoint|weight|model_url|download_url", re.IGNORECASE
)
COMMIT_OBJECT_PATTERN = re.compile(
    r"^(?:unreachable|dangling) commit ([0-9a-f]{40})$"
)


def run_command(
    command: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def git_output(root: Path, *arguments: str) -> tuple[int, str, str]:
    result = run_command(["git", "-C", str(root), *arguments])
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def within_window(value: str, *, after: str, before: str) -> bool:
    timestamp = parse_iso(value)
    return parse_iso(after) <= timestamp <= parse_iso(before)


def extract_reference_lines(content: str, *, limit: int = 80) -> list[str]:
    lines = [
        line.strip()
        for line in content.splitlines()
        if REFERENCE_PATTERN.search(line)
    ]
    return lines[:limit]


def parse_commit_metadata(root: Path, sha: str) -> dict[str, str] | None:
    code, output, _ = git_output(
        root,
        "show",
        "-s",
        "--format=%H%x1f%cI%x1f%s",
        sha,
    )
    if code != 0 or not output:
        return None
    parts = output.split("\x1f", maxsplit=2)
    if len(parts) != 3:
        return None
    return {"commit": parts[0], "committed_at": parts[1], "subject": parts[2]}


def collect_source_snapshot(root: Path, sha: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_path in SOURCE_PATHS:
        code, content, error = git_output(root, "show", f"{sha}:{source_path}")
        if code != 0:
            records.append(
                {
                    "path": source_path,
                    "exists": False,
                    "error": error or None,
                }
            )
            continue
        records.append(
            {
                "path": source_path,
                "exists": True,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "reference_lines": extract_reference_lines(content),
            }
        )
    return records


def parse_refs(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t", maxsplit=3)
        if len(parts) != 4:
            continue
        records.append(
            {
                "ref": parts[0],
                "object": parts[1],
                "committed_at": parts[2],
                "subject": parts[3],
            }
        )
    return records


def parse_reflog(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\x1f", maxsplit=2)
        if len(parts) != 3:
            continue
        records.append(
            {"commit": parts[0], "selector": parts[1], "message": parts[2]}
        )
    return records


def collect_repository(
    root: Path,
    *,
    after: str,
    before: str,
    max_candidates: int,
    skip_fsck: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(root),
        "exists": root.exists(),
        "is_git_repository": False,
    }
    if not root.exists():
        return report

    code, inside, error = git_output(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside != "true":
        report["git_error"] = error or "not a Git worktree"
        return report
    report["is_git_repository"] = True

    def capture(*arguments: str) -> str | None:
        result_code, stdout, _ = git_output(root, *arguments)
        return stdout if result_code == 0 else None

    head = capture("rev-parse", "HEAD")
    report.update(
        {
            "git_dir": capture("rev-parse", "--git-dir"),
            "head": head,
            "branch": capture("branch", "--show-current"),
            "describe": capture("describe", "--always", "--dirty", "--tags"),
            "status": capture("status", "--short", "--branch"),
            "remotes": capture("remote", "-v"),
        }
    )

    ref_format = (
        "%(refname)\t%(objectname)\t"
        "%(committerdate:iso-strict)\t%(subject)"
    )
    _, refs_output, _ = git_output(
        root,
        "for-each-ref",
        f"--format={ref_format}",
    )
    refs = parse_refs(refs_output)
    report["refs"] = refs

    _, reflog_output, reflog_error = git_output(
        root,
        "reflog",
        "show",
        "--all",
        "--date=iso-strict",
        "--format=%H%x1f%gD%x1f%gs",
    )
    reflog = parse_reflog(reflog_output)
    report["reflog"] = reflog
    if reflog_error and not reflog:
        report["reflog_error"] = reflog_error

    unreachable: list[str] = []
    if not skip_fsck:
        _, fsck_output, fsck_error = git_output(
            root,
            "fsck",
            "--full",
            "--unreachable",
            "--no-reflogs",
        )
        for line in fsck_output.splitlines():
            match = COMMIT_OBJECT_PATTERN.match(line.strip())
            if match:
                unreachable.append(match.group(1))
        report["unreachable_commit_count"] = len(unreachable)
        if fsck_error:
            report["fsck_stderr"] = fsck_error
    else:
        report["fsck_skipped"] = True

    origins: dict[str, set[str]] = defaultdict(set)
    if head:
        origins[head].add("head")
    for record in refs:
        origins[record["object"]].add(f"ref:{record['ref']}")
    for record in reflog:
        origins[record["commit"]].add(f"reflog:{record['selector']}")
    for sha in unreachable:
        origins[sha].add("unreachable")

    candidates: list[dict[str, Any]] = []
    for sha, sha_origins in origins.items():
        object_code, object_type, _ = git_output(root, "cat-file", "-t", sha)
        if object_code != 0 or object_type != "commit":
            continue
        metadata = parse_commit_metadata(root, sha)
        if metadata is None or not within_window(
            metadata["committed_at"], after=after, before=before
        ):
            continue
        candidates.append(
            {
                **metadata,
                "origins": sorted(sha_origins),
                "source_snapshot": collect_source_snapshot(root, sha),
            }
        )

    candidates.sort(
        key=lambda item: (item["committed_at"], item["commit"]), reverse=True
    )
    report["historical_window"] = {"after": after, "before": before}
    report["historical_candidates"] = candidates[: max(max_candidates, 0)]
    report["historical_candidate_count_before_limit"] = len(candidates)
    return report


def model_file_relevant(path: Path, *, broad_repo_scan: bool) -> bool:
    name = path.name.lower()
    if path.suffix.lower() not in MODEL_SUFFIXES and "segnet" not in name:
        return False
    if broad_repo_scan:
        return True
    return "segnet" in name or "homr" in name


def iter_model_files(root: Path, *, broad_repo_scan: bool) -> Iterable[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    try:
        for path in root.rglob("*"):
            try:
                if path.is_file() and model_file_relevant(
                    path, broad_repo_scan=broad_repo_scan
                ):
                    files.append(path)
            except OSError:
                continue
    except OSError:
        return files
    return files


def collect_model_artifacts(
    roots: list[tuple[Path, bool]], *, max_size_bytes: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root, broad_repo_scan in roots:
        for path in iter_model_files(root, broad_repo_scan=broad_repo_scan):
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                stat = path.stat()
            except OSError as error:
                records.append({"path": resolved, "error": str(error)})
                continue
            record: dict[str, Any] = {
                "path": resolved,
                "scan_root": str(root),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .isoformat(),
            }
            if stat.st_size <= max_size_bytes:
                try:
                    record["sha256"] = sha256_file(path)
                except OSError as error:
                    record["sha256_error"] = str(error)
            else:
                record["sha256_skipped"] = "file exceeds max-size limit"
            records.append(record)
    records.sort(
        key=lambda item: (item.get("modified_at", ""), item["path"]),
        reverse=True,
    )
    return records


def deduplicate_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser().resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(key))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-repo-root", type=Path, default=DEFAULT_MAIN_REPO)
    parser.add_argument("--root", action="append", type=Path, default=[])
    parser.add_argument("--cache-root", action="append", type=Path, default=[])
    parser.add_argument("--after", default=DEFAULT_AFTER)
    parser.add_argument("--before", default=DEFAULT_BEFORE)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--max-model-size-mb", type=int, default=1024)
    parser.add_argument("--skip-fsck", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    issue_root_result = run_command(
        ["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd()
    )
    if issue_root_result.returncode != 0:
        message = issue_root_result.stderr.strip() or "not inside a Git worktree"
        raise RuntimeError(message)
    issue_root = Path(issue_root_result.stdout.strip()).resolve()
    main_repo = args.main_repo_root.expanduser().resolve()

    repository_roots = deduplicate_paths(
        [
            *args.root,
            issue_root / "external/homr",
            issue_root / "homr",
            main_repo / "external/homr",
            main_repo / "homr",
        ]
    )
    cache_roots = deduplicate_paths(
        [
            *args.cache_root,
            Path.home() / ".cache/homr",
            Path.home() / ".homr",
            Path.home() / ".local/share/homr",
            Path.home() / ".cache/torch/hub/checkpoints",
        ]
    )

    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else main_repo / DEFAULT_OUTPUT_REL
    )

    repositories = [
        collect_repository(
            root,
            after=args.after,
            before=args.before,
            max_candidates=args.max_candidates,
            skip_fsck=args.skip_fsck,
        )
        for root in repository_roots
    ]
    model_scan_roots = [(root, True) for root in repository_roots] + [
        (root, False) for root in cache_roots
    ]
    model_artifacts = collect_model_artifacts(
        model_scan_roots,
        max_size_bytes=max(args.max_model_size_mb, 0) * 1024 * 1024,
    )

    report = {
        "schema_version": "issue245.local_homr_provenance.v1",
        "status": "completed",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "issue_worktree": str(issue_root),
        "main_repo": str(main_repo),
        "repository_roots": [str(path) for path in repository_roots],
        "cache_roots": [str(path) for path in cache_roots],
        "repositories": repositories,
        "model_artifacts": model_artifacts,
        "limitations": [
            "Only the listed HOMR repository and cache roots are inspected.",
            "Shell history and unrelated personal files are not inspected.",
            (
                "Expired reflog entries, pruned Git objects, deleted Docker layers, "
                "and removed model files cannot be recovered by this inventory."
            ),
            (
                "A discovered commit or model file is provenance evidence only; "
                "it is not selected as a production input."
            ),
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    git_repositories = sum(
        1 for item in repositories if item["is_git_repository"]
    )
    candidate_count = sum(
        len(item.get("historical_candidates", [])) for item in repositories
    )
    print(f"Git repositories found: {git_repositories}")
    print(f"Historical candidate commits: {candidate_count}")
    print(f"Model artifacts found: {len(model_artifacts)}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
