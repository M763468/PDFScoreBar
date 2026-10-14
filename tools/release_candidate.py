#!/usr/bin/env python3
"""Create and verify a pinned, minimal release commit without changing shared branches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from materialize_distribution import MANIFEST, PROVENANCE, ROOT, check_tree, selected_files


def git(repository: Path, *args: str, data: bytes | None = None, env: dict | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *args],
        input=data,
        capture_output=True,
        check=True,
        env=env,
    ).stdout


def commit_id(repository: Path, value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Use a full, frozen 40-character commit SHA, not a mutable ref")
    if git(repository, "rev-parse", "--verify", value + "^{commit}").decode().strip() != value:
        raise ValueError(f"Not a commit: {value}")
    return value


def source_files(repository: Path, commit: str) -> dict[str, tuple[str, str]]:
    entries = {}
    for row in git(repository, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            entries[path.decode()] = (mode, oid) if kind == "blob" else (mode, "")
    return entries


def snapshot(repository: Path, source_commit: str, main_commit: str) -> tuple[dict, dict]:
    source_commit = commit_id(repository, source_commit)
    main_commit = commit_id(repository, main_commit)
    entries = source_files(repository, source_commit)
    if entries.get(MANIFEST, (None,))[0] != "100644":
        raise ValueError("The committed distribution manifest must be a regular file")
    manifest = json.loads(git(repository, "cat-file", "blob", entries[MANIFEST][1]))
    if manifest.get("schema_version") != 3:
        raise ValueError("Unsupported distribution manifest schema; expected version 3")
    paths = selected_files(manifest)
    if MANIFEST not in paths:
        raise ValueError("The distribution must include its own manifest")
    content, modes = {}, {}
    for path in paths:
        mode, oid = entries.get(path, (None, None))
        if mode not in {"100644", "100755"}:
            raise ValueError(f"Missing or unsafe committed distribution file: {path}")
        content[path] = git(repository, "cat-file", "blob", oid)
        modes[path] = mode
    timestamp = git(repository, "show", "-s", "--format=%ct", source_commit).decode().strip()
    provenance = {
        "schema_version": 1,
        "source_commit": source_commit,
        "source_branch": "detached",
        "source_dirty": False,
        "files": {path: hashlib.sha256(value).hexdigest() for path, value in content.items()},
        "release": {
            "schema_version": 1,
            "source_tree": git(repository, "rev-parse", source_commit + "^{tree}").decode().strip(),
            "main_parent": main_commit,
            "source_timestamp": timestamp,
            "manifest_sha256": hashlib.sha256(content[MANIFEST]).hexdigest(),
            "manifest_schema_version": manifest["schema_version"],
            "file_modes": modes,
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "checker_sha256": hashlib.sha256(
                Path(__file__).with_name("materialize_distribution.py").read_bytes()
            ).hexdigest(),
        },
    }
    content[PROVENANCE] = (json.dumps(provenance, indent=2) + "\n").encode()
    return content, provenance


def write_snapshot(destination: Path, content: dict, provenance: dict) -> None:
    for path, value in content.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        target.chmod(0o755 if provenance["release"]["file_modes"].get(path) == "100755" else 0o644)


def commit_environment(provenance: dict) -> dict:
    env = os.environ.copy()
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = "PDFScoreBar Release"
        env[f"GIT_{role}_EMAIL"] = "release@pdfscorebar.invalid"
        env[f"GIT_{role}_DATE"] = provenance["release"]["source_timestamp"] + " +0000"
    return env


def commit_message(provenance: dict) -> bytes:
    return (
        f"Release candidate from {provenance['source_commit']}\n\n"
        f"Main parent: {provenance['release']['main_parent']}\n"
        f"Manifest SHA-256: {provenance['release']['manifest_sha256']}\n"
    ).encode()


def create_candidate(
    repository: Path, destination: Path, source_commit: str, main_commit: str, branch: str
) -> dict:
    repository, destination = repository.resolve(), destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Candidate destination already exists; use a fresh path")
    if destination.resolve().is_relative_to(repository):
        raise ValueError("Candidate must be outside the source checkout")
    if not branch.startswith("release/"):
        raise ValueError("Candidate branch must be versioned under release/")
    git(repository, "check-ref-format", "--branch", branch)
    content, provenance = snapshot(repository, source_commit, main_commit)
    # Validate before creating Git metadata or publishing a partial candidate.
    with tempfile.TemporaryDirectory(prefix="pdfscore-release-check-") as temp:
        extracted = Path(temp)
        write_snapshot(extracted, content, provenance)
        errors = check_tree(extracted)
        if errors:
            raise ValueError("Candidate check failed:\n" + "\n".join(errors))
    destination.mkdir(parents=True)
    git(destination, "init", "--quiet", "--template=")
    # Copy the main parent into this independent repository; no source alternates/mount are needed.
    git(destination, "fetch", "--quiet", "--no-tags", "--depth=1", str(repository), main_commit)
    git(destination, "read-tree", "--empty")
    index = []
    for path, value in content.items():
        oid = git(destination, "hash-object", "-w", "--stdin", data=value).decode().strip()
        mode = provenance["release"]["file_modes"].get(path, "100644")
        index.append(f"{mode} {oid}\t{path}\0".encode())
    git(destination, "update-index", "-z", "--index-info", data=b"".join(index))
    tree = git(destination, "write-tree").decode().strip()
    candidate_commit = (
        git(
            destination,
            "commit-tree",
            tree,
            "-p",
            main_commit,
            data=commit_message(provenance),
            env=commit_environment(provenance),
        )
        .decode()
        .strip()
    )
    git(destination, "update-ref", "refs/heads/" + branch, candidate_commit)
    git(destination, "symbolic-ref", "HEAD", "refs/heads/" + branch)
    git(destination, "checkout-index", "--all", "--force")
    return check_candidate(repository, destination, source_commit, main_commit)


def check_candidate(
    repository: Path, candidate: Path, source_commit: str, main_commit: str
) -> dict:
    candidate = candidate.resolve()
    if Path(git(candidate, "rev-parse", "--show-toplevel").decode().strip()).resolve() != candidate:
        raise ValueError("Candidate must be the root of its own Git checkout")
    content, expected = snapshot(repository, source_commit, main_commit)
    errors = check_tree(candidate, git_checkout=True)
    if errors:
        raise ValueError("Candidate check failed:\n" + "\n".join(errors))
    if (candidate / PROVENANCE).read_bytes() != content[PROVENANCE]:
        raise ValueError(
            "Candidate provenance differs from the pinned source/main/generator identities"
        )
    if git(candidate, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Candidate checkout must be clean")
    head = git(candidate, "rev-parse", "HEAD").decode().strip()
    parents = git(candidate, "show", "-s", "--format=%P", head).decode().strip().split()
    if parents != [main_commit]:
        raise ValueError("Candidate must have exactly the frozen main commit as its parent")
    tracked = source_files(candidate, head)
    if set(tracked) != set(content):
        raise ValueError("Candidate tracked file set differs from the distribution")
    for path, value in content.items():
        mode, oid = tracked[path]
        if mode != expected["release"]["file_modes"].get(path, "100644"):
            raise ValueError(f"Candidate file mode mismatch: {path}")
        if bool((candidate / path).stat().st_mode & 0o111) != (mode == "100755"):
            raise ValueError(f"Candidate working file mode mismatch: {path}")
        if git(candidate, "cat-file", "blob", oid) != value:
            raise ValueError(f"Candidate differs from pinned source: {path}")
    # Recompute the canonical commit identity as well as checking content and parentage.
    tree = git(candidate, "rev-parse", head + "^{tree}").decode().strip()
    canonical = (
        git(
            candidate,
            "commit-tree",
            tree,
            "-p",
            main_commit,
            data=commit_message(expected),
            env=commit_environment(expected),
        )
        .decode()
        .strip()
    )
    if head != canonical:
        raise ValueError("Candidate commit metadata differs from its deterministic identity")
    return {
        "schema_version": 1,
        "source_commit": source_commit,
        "main_parent": main_commit,
        "candidate_commit": head,
        "candidate_tree": tree,
        "manifest_sha256": expected["release"]["manifest_sha256"],
        "manifest_schema_version": expected["release"]["manifest_schema_version"],
        "shipped_files": len(expected["files"]),
        "static_checks": "PASS",
        "release_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "check"):
        command = commands.add_parser(name)
        command.add_argument("destination", type=Path)
        command.add_argument("--source-commit", required=True)
        command.add_argument("--main-commit", required=True)
        command.add_argument(
            "--report", type=Path, help="Write static evidence outside the candidate"
        )
        if name == "create":
            command.add_argument("--branch", required=True)
    args = parser.parse_args()
    try:
        if args.report and args.report.resolve().is_relative_to(args.destination.resolve()):
            raise ValueError("Validation reports must stay outside the exact candidate tree")
        if args.command == "create":
            report = create_candidate(
                args.repository, args.destination, args.source_commit, args.main_commit, args.branch
            )
        else:
            report = check_candidate(
                args.repository, args.destination, args.source_commit, args.main_commit
            )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, KeyError, SyntaxError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
