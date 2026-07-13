#!/usr/bin/env python3
"""Discover distinct PDFScoreBar evaluator source snapshots before an artifact run.

This is lightweight Issue #245 investigation tooling. It only reads Git history
and writes a machine-readable candidate report under ignored ``logs/`` paths.
It does not run HOMR or modify a production configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

DEFAULT_ARTIFACT_TIME = "2026-01-31T10:34:21+09:00"
DEFAULT_AFTER_TIME = "2026-01-01T00:00:00+09:00"
DEFAULT_OUTPUT_REL = Path(
    "logs/issue245_pdfscore_evaluator_ref_discovery/"
    "evaluator_ref_candidates.json"
)
SOURCE_FILES = (
    "src/homr_eval_scripts/homr_evaluator.py",
    "src/common/preprocessing.py",
    "src/common/thin_barline_finder.py",
    "src/common/barline_evaluation.py",
)
FIELD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    committed_at: str
    subject: str


def git_output(repo: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_commit_lines(output: str) -> list[CommitRecord]:
    records: list[CommitRecord] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(FIELD_SEPARATOR, maxsplit=2)
        if len(parts) != 3:
            raise ValueError(f"Unexpected git log record: {line!r}")
        records.append(CommitRecord(*parts))
    return records


def commit_metadata(repo: Path, ref: str) -> CommitRecord:
    output = git_output(
        repo,
        "show",
        "-s",
        f"--format=%H{FIELD_SEPARATOR}%cI{FIELD_SEPARATOR}%s",
        ref,
    )
    records = parse_commit_lines(output)
    if len(records) != 1:
        raise RuntimeError(f"Expected one commit for {ref!r}, got {len(records)}")
    return records[0]


def blob_oid(repo: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", f"{commit}:{path}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def source_snapshot(repo: Path, commit: CommitRecord) -> dict[str, Any]:
    blobs = [
        {"path": path, "blob_oid": blob_oid(repo, commit.sha, path)}
        for path in SOURCE_FILES
    ]
    signature_payload = json.dumps(blobs, sort_keys=True, separators=(",", ":"))
    signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()
    return {
        "commit": commit.sha,
        "committed_at": commit.committed_at,
        "subject": commit.subject,
        "source_signature": signature,
        "source_blobs": blobs,
    }


def discover_touching_commits(
    repo: Path,
    *,
    after_time: str,
    artifact_time: str,
) -> list[CommitRecord]:
    output = git_output(
        repo,
        "log",
        "--first-parent",
        "--reverse",
        f"--after={after_time}",
        f"--before={artifact_time}",
        f"--format=%H{FIELD_SEPARATOR}%cI{FIELD_SEPARATOR}%s",
        "--",
        *SOURCE_FILES,
    )
    return parse_commit_lines(output)


def group_distinct_snapshots(
    snapshots: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for snapshot in snapshots:
        signature = str(snapshot["source_signature"])
        if signature not in grouped:
            grouped[signature] = {
                "source_signature": signature,
                "source_blobs": snapshot["source_blobs"],
                "commits": [],
            }
            order.append(signature)
        grouped[signature]["commits"].append(
            {
                "commit": snapshot["commit"],
                "committed_at": snapshot["committed_at"],
                "subject": snapshot["subject"],
            }
        )

    distinct: list[dict[str, Any]] = []
    for signature in reversed(order):
        group = grouped[signature]
        newest = group["commits"][-1]
        oldest = group["commits"][0]
        distinct.append(
            {
                "candidate_ref": newest["commit"],
                "newest_commit": newest,
                "oldest_commit": oldest,
                "equivalent_touching_commits": group["commits"],
                "source_signature": group["source_signature"],
                "source_blobs": group["source_blobs"],
            }
        )
    return distinct


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--artifact-time", default=DEFAULT_ARTIFACT_TIME)
    parser.add_argument("--after-time", default=DEFAULT_AFTER_TIME)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=4,
        help="Number of newest distinct snapshots to mark for focused inference.",
    )
    args = parser.parse_args()

    repo = (
        args.repo_root.resolve()
        if args.repo_root is not None
        else Path(git_output(Path.cwd(), "rev-parse", "--show-toplevel"))
    )
    output = (
        args.output.resolve()
        if args.output is not None
        else repo / DEFAULT_OUTPUT_REL
    )

    boundary_sha = git_output(
        repo,
        "rev-list",
        "--first-parent",
        "-1",
        f"--before={args.artifact_time}",
        "HEAD",
    )
    if not boundary_sha:
        raise RuntimeError(
            f"No first-parent commit found at or before {args.artifact_time}"
        )
    boundary = commit_metadata(repo, boundary_sha)

    touching_commits = discover_touching_commits(
        repo,
        after_time=args.after_time,
        artifact_time=args.artifact_time,
    )
    commits_by_sha = {record.sha: record for record in touching_commits}
    commits_by_sha.setdefault(boundary.sha, boundary)
    ordered_commits = sorted(
        commits_by_sha.values(),
        key=lambda record: (record.committed_at, record.sha),
    )
    snapshots = [source_snapshot(repo, record) for record in ordered_commits]
    distinct = group_distinct_snapshots(snapshots)

    for index, candidate in enumerate(distinct):
        candidate["focused_candidate"] = index < max(args.candidate_limit, 0)
        candidate["candidate_rank_newest_first"] = index + 1

    report = {
        "schema_version": "issue245.pdfscore_evaluator_ref_discovery.v1",
        "artifact_time": args.artifact_time,
        "after_time": args.after_time,
        "repo_root": str(repo),
        "head": git_output(repo, "rev-parse", "HEAD"),
        "artifact_boundary_commit": {
            "commit": boundary.sha,
            "committed_at": boundary.committed_at,
            "subject": boundary.subject,
        },
        "source_files": list(SOURCE_FILES),
        "touching_commit_count": len(touching_commits),
        "snapshot_count_including_boundary": len(snapshots),
        "distinct_snapshot_count": len(distinct),
        "candidates": distinct,
        "limitations": [
            "Only commits reachable from the current branch first-parent history are inspected.",
            "Uncommitted working-tree changes used by the historical run cannot be recovered from Git history.",
            "This report identifies tracked source snapshots only; it does not identify the untracked external/homr checkout.",
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Artifact boundary: {boundary.sha} {boundary.committed_at} {boundary.subject}")
    print(f"Distinct source snapshots: {len(distinct)}")
    for candidate in distinct[: max(args.candidate_limit, 0)]:
        newest = candidate["newest_commit"]
        print(
            "Candidate: "
            f"{candidate['candidate_ref']} {newest['committed_at']} "
            f"{newest['subject']} signature={candidate['source_signature'][:12]}"
        )
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
