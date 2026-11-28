#!/usr/bin/env python3
"""CI-only license fixture commit that lets PR checks exercise the main license overlay.

``main`` carries license material that ``develop`` never does, so a plain promotion candidate
is refused (#558). CI still has to generate promotion-shaped candidates from every PR source
without a maintainer re-authoring the private license commit for each README edit. This tool
writes, as unreferenced Git objects only, a deterministic commit on the PR source that carries
the current ``main`` license material:

- policy additions present on ``main`` are copied byte-for-byte from ``main``;
- policy modifications replay ``main``'s license change (recorded base -> ``main``) onto the
  source with a three-way merge. Where it conflicts with the PR's own edit (for example the
  README translation-hash line), the hunks of both sides are kept (``--union``) and the path is
  reported: a real promotion must re-author it, which the strict ``derive-overlay`` enforces.

The commit is then fed to the unchanged ``release_candidate.py derive-overlay`` (first-application
form), ``create`` and ``check``, so every fail-closed overlay check still runs. It is never a
release input: real promotions derive from the private license commit or the promoted ``main``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_candidate as rc
from materialize_distribution import ROOT, overlay_policy

FIXTURE_IDENTITY = ("PDFScoreBar CI license fixture", "ci-license-fixture@pdfscorebar.invalid")


def merge(current: bytes, base: bytes, licensed: bytes, union: bool) -> tuple[int, bytes]:
    with tempfile.TemporaryDirectory(prefix="pdfscore-ci-license-merge-") as temp:
        files = []
        for name, value in (("current", current), ("base", base), ("licensed", licensed)):
            file = Path(temp) / name
            file.write_bytes(value)
            files.append(str(file))
        result = subprocess.run(
            ["git", "merge-file", "-p", *(["--union"] if union else []), *files],
            capture_output=True,
            env=rc.isolated_environment(),
        )
    if result.returncode < 0 or result.returncode > 127:
        raise ValueError(f"git merge-file failed: {result.stderr.decode()}")
    return result.returncode, result.stdout


def write_commit(repository: Path, source: str, changes: dict[str, tuple[str, bytes]]) -> str:
    """Create the fixture commit through a private index; refs, index and worktree are untouched."""
    with tempfile.TemporaryDirectory(prefix="pdfscore-ci-license-index-") as temp:
        env = rc.isolated_environment()
        env["GIT_INDEX_FILE"] = str(Path(temp) / "index")

        def run(*args: str, data: bytes | None = None) -> str:
            return subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *args],
                input=data,
                capture_output=True,
                check=True,
                env=env,
            ).stdout.decode()

        run("read-tree", source)
        for path, (mode, value) in sorted(changes.items()):
            oid = run("hash-object", "-w", "--stdin", data=value).strip()
            run("update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")
        tree = run("write-tree").strip()
        timestamp = run("show", "-s", "--format=%ct", source).strip()
        for role in ("AUTHOR", "COMMITTER"):
            env[f"GIT_{role}_NAME"], env[f"GIT_{role}_EMAIL"] = FIXTURE_IDENTITY
            env[f"GIT_{role}_DATE"] = timestamp + " +0000"
        message = f"CI license fixture for {source}\n\nNever a release input.\n".encode()
        return run("commit-tree", tree, "-p", source, data=message).strip()


def fixture_commit(repository: Path, source_commit: str, main_commit: str) -> dict:
    repository = repository.resolve()
    source_commit = rc.commit_id(repository, source_commit)
    main_commit = rc.commit_id(repository, main_commit)
    source = rc.source_files(repository, source_commit)
    manifest = rc.committed_manifest(repository, source)
    required = rc.main_license_paths(repository, main_commit, manifest)
    report = {
        "schema_version": 1,
        "source_commit": source_commit,
        "main_commit": main_commit,
        "main_license": bool(required),
        "license_commit": None,
    }
    if not required:
        return report
    main = rc.source_files(repository, main_commit)
    previous = rc.previous_overlay(repository, main)
    if previous is None:
        raise ValueError(
            "Main carries license material without a recorded overlay; CI cannot replay it"
        )
    base_commit = rc.commit_id(repository, previous["derived_from"]["source_commit"])
    base = rc.source_files(repository, base_commit)
    additions, modifications = overlay_policy(manifest)
    outside = sorted(required - set(additions) - modifications)
    if outside:
        raise ValueError(f"Main license material outside the develop overlay policy: {outside}")
    changes, copied, modified, union_merged = {}, [], [], []
    for path in sorted(required):
        licensed = rc.committed_blob(repository, main, path)
        if licensed is None:
            raise ValueError(f"Recorded main license path is missing on main: {path}")
        if path in additions:
            mode = main[path][0]
            changes[path] = (mode, licensed)
            copied.append(path)
            continue
        old = rc.committed_blob(repository, base, path)
        current = rc.committed_blob(repository, source, path)
        if old is None or current is None:
            raise ValueError(f"License modification target missing in base or source: {path}")
        if licensed == old:
            continue
        value = licensed
        if current != old:
            status, value = merge(current, old, licensed, union=False)
            if status:
                _, value = merge(current, old, licensed, union=True)
                union_merged.append(path)
        changes[path] = (source[path][0], value)
        modified.append(path)
    report.update(
        main_overlay_source=base_commit,
        license_commit=write_commit(repository, source_commit, changes),
        copied=copied,
        modified=modified,
        union_merged=union_merged,
    )
    return report


def verify_candidate(repository: Path, candidate: Path, main_commit: str) -> dict:
    """Every main license path survives; added license material is byte-identical to main."""
    repository = repository.resolve()
    main_commit = rc.commit_id(repository, main_commit)
    main = rc.source_files(repository, main_commit)
    tracked = rc.source_files(candidate.resolve(), "HEAD")
    candidate_manifest = rc.committed_manifest(candidate.resolve(), tracked)
    required = rc.main_license_paths(repository, main_commit, candidate_manifest)
    additions, _ = overlay_policy(candidate_manifest)
    missing = sorted(required - set(tracked))
    changed = sorted(
        path
        for path in required & set(additions)
        if path in tracked
        and rc.committed_blob(candidate, tracked, path) != rc.committed_blob(repository, main, path)
    )
    if missing or changed:
        raise ValueError(
            f"Candidate lost main license material: missing={missing} changed={changed}"
        )
    return {"main_commit": main_commit, "kept": sorted(required)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("commit", help="Write the CI license fixture commit")
    create.add_argument("--source-commit", required=True)
    create.add_argument("--main-commit", required=True)
    create.add_argument("--report", type=Path)
    verify = commands.add_parser("verify", help="Check a candidate kept main's license material")
    verify.add_argument("candidate", type=Path)
    verify.add_argument("--main-commit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "commit":
            report = fixture_commit(args.repository, args.source_commit, args.main_commit)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, indent=2) + "\n")
        else:
            report = verify_candidate(args.repository, args.candidate, args.main_commit)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
