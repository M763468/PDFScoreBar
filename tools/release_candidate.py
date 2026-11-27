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
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import materialize_distribution
from materialize_distribution import (
    MANIFEST,
    PROVENANCE,
    ROOT,
    canonical_json,
    check_tree,
    exact_path,
    overlay_changes,
    overlay_policy,
    selected_files,
)

OVERLAY_SPEC = "MAIN_LICENSE_OVERLAY.json"
OVERLAY_FILES = "files"
# Conventional license file names that, on main, must never silently disappear.
LICENSE_NAMES = {"LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "NOTICE"}


@cache
def repository_env_vars() -> frozenset[str]:
    """Git's own list of repository-local variables, plus the ones that select a repository."""
    listed = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True
    ).stdout.split()
    return frozenset(("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", *listed))


def isolated_environment(base: dict | None = None) -> dict:
    """Drop inherited repository-selecting variables so ``git -C`` names the only repository.

    GIT_DIR/GIT_WORK_TREE outrank ``-C``; when inherited (a container mapping, a Git hook) they
    would redirect ``init``/``commit`` meant for the candidate into the caller's checkout.
    """
    env = dict(os.environ if base is None else base)
    for name in repository_env_vars():
        env.pop(name, None)
    return env


def git(repository: Path, *args: str, data: bytes | None = None, env: dict | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *args],
        input=data,
        capture_output=True,
        check=True,
        env=isolated_environment(env),
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


def pinned_tool_hashes(repository: Path, entries: dict) -> dict[str, str]:
    """Require the running generator/checker to match the frozen source tools."""
    hashes = {}
    for role, path in (
        ("generator", Path(__file__)),
        ("checker", Path(materialize_distribution.__file__)),
    ):
        source_path = "tools/" + path.name
        mode, oid = entries.get(source_path, (None, None))
        if mode not in {"100644", "100755"}:
            raise ValueError(f"Missing or unsafe pinned release tool: {source_path}")
        pinned = git(repository, "cat-file", "blob", oid)
        if path.read_bytes() != pinned:
            raise ValueError(
                f"Running release tool differs from pinned source: {source_path}; "
                "run the tools from a checkout of the source commit"
            )
        hashes[role] = hashlib.sha256(pinned).hexdigest()
    return hashes


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def committed_blob(repository: Path, entries: dict, path: str) -> bytes | None:
    mode, oid = entries.get(path, (None, None))
    if mode is None:
        return None
    if mode not in {"100644", "100755"}:
        raise ValueError(f"Unsafe committed file: {path}")
    return git(repository, "cat-file", "blob", oid)


def committed_manifest(repository: Path, entries: dict) -> dict:
    if entries.get(MANIFEST, (None,))[0] != "100644":
        raise ValueError("The committed distribution manifest must be a regular file")
    manifest = json.loads(git(repository, "cat-file", "blob", entries[MANIFEST][1]))
    if manifest.get("schema_version") != 3:
        raise ValueError("Unsupported distribution manifest schema; expected version 3")
    return manifest


def previous_overlay(repository: Path, entries: dict) -> dict | None:
    """The main license overlay recorded by a promoted commit's provenance, if any."""
    value = committed_blob(repository, entries, PROVENANCE)
    if value is None:
        return None
    try:
        overlay = json.loads(value).get("release", {}).get("main_overlay")
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Unreadable provenance in main parent: {exc}") from exc
    return overlay["spec"] if overlay else None


def main_license_paths(repository: Path, main_commit: str, manifest: dict) -> set[str]:
    """Paths of main-only license material on the parent that the candidate must keep."""
    entries = source_files(repository, main_commit)
    additions, _ = overlay_policy(manifest)
    required = {
        path
        for path in entries
        if path in additions or path in LICENSE_NAMES or path.startswith("LICENSES/")
    }
    spec = previous_overlay(repository, entries)
    if spec:
        required |= {entry["path"] for entry in spec["entries"]}
    return required


def snapshot(
    repository: Path,
    source_commit: str,
    main_commit: str,
    overlay: tuple[dict, dict[str, bytes]] | None = None,
) -> tuple[dict, dict]:
    source_commit = commit_id(repository, source_commit)
    main_commit = commit_id(repository, main_commit)
    entries = source_files(repository, source_commit)
    tool_hashes = pinned_tool_hashes(repository, entries)
    manifest = committed_manifest(repository, entries)
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
    required = main_license_paths(repository, main_commit, manifest)
    main_overlay = None
    if overlay is None:
        if required:
            raise ValueError(
                "Main parent carries main-only license material "
                f"{sorted(required)}; supply the reviewed --license-overlay to keep it"
            )
    else:
        spec, overlay_content = overlay
        added, modified = overlay_changes(spec, manifest)
        dropped = required - added - modified
        if dropped:
            raise ValueError(
                f"License overlay would drop main-only license material: {sorted(dropped)}"
            )
        for entry in spec["entries"]:
            path, value = entry["path"], overlay_content.get(entry["path"])
            if value is None or sha256(value) != entry["sha256"]:
                raise ValueError(f"License overlay content hash mismatch: {path}")
            if entry["operation"] == "modify":
                actual = sha256(content[path])
                if actual != entry["base_sha256"]:
                    raise ValueError(
                        f"License overlay is stale for {path}: sealed against develop SHA-256 "
                        f"{entry['base_sha256']}, but the source selects {actual}; re-derive it "
                        "so newer develop changes are not overwritten"
                    )
            else:
                modes[path] = "100644"
            content[path] = value
        content = dict(sorted(content.items()))
        modes = dict(sorted(modes.items()))
        main_overlay = {"spec": spec, "spec_sha256": sha256(canonical_json(spec))}
    timestamp = git(repository, "show", "-s", "--format=%ct", source_commit).decode().strip()
    provenance = {
        "schema_version": 1,
        "source_commit": source_commit,
        "source_branch": "detached",
        "source_dirty": False,
        "files": {path: sha256(value) for path, value in content.items()},
        "release": {
            "schema_version": 1,
            "source_tree": git(repository, "rev-parse", source_commit + "^{tree}").decode().strip(),
            "main_parent": main_commit,
            "source_timestamp": timestamp,
            "manifest_sha256": sha256(content[MANIFEST]),
            "manifest_schema_version": manifest["schema_version"],
            "file_modes": modes,
            "generator_sha256": tool_hashes["generator"],
            "checker_sha256": tool_hashes["checker"],
        },
    }
    if main_overlay:
        provenance["release"]["main_overlay"] = main_overlay
    content[PROVENANCE] = (json.dumps(provenance, indent=2) + "\n").encode()
    return content, provenance


def load_overlay(directory: Path) -> tuple[dict, dict[str, bytes]]:
    """Read a sealed overlay package: canonical spec plus exactly its declared files."""
    directory = directory.resolve()
    spec_path = directory / OVERLAY_SPEC
    if not spec_path.is_file() or spec_path.is_symlink():
        raise ValueError(f"License overlay spec is missing: {spec_path}")
    raw = spec_path.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict) or raw != canonical_json(spec):
        raise ValueError("License overlay spec must be canonical JSON written by derive-overlay")
    contents = {}
    for entry in spec.get("entries") or []:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not exact_path(path):
            raise ValueError(f"Invalid license overlay path: {path}")
        file = directory / OVERLAY_FILES / path
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(directory):
            raise ValueError(f"Missing or unsafe license overlay file: {path}")
        contents[path] = file.read_bytes()
    actual = {
        item.relative_to(directory).as_posix()
        for item in directory.rglob("*")
        if item.is_file() or item.is_symlink()
    }
    unexpected = actual - {OVERLAY_SPEC} - {f"{OVERLAY_FILES}/{path}" for path in contents}
    if unexpected:
        raise ValueError(f"Unexpected license overlay files: {sorted(unexpected)}")
    return spec, contents


def candidate_overlay(candidate: Path) -> tuple[dict, dict[str, bytes]] | None:
    """Rebuild the overlay a candidate declares, so check can re-derive it from develop."""
    provenance = json.loads((candidate / PROVENANCE).read_text(encoding="utf-8"))
    overlay = provenance.get("release", {}).get("main_overlay")
    if overlay is None:
        return None
    contents = {}
    for entry in overlay["spec"]["entries"]:
        file = candidate / entry["path"]
        if not exact_path(entry["path"]) or not file.is_file() or file.is_symlink():
            raise ValueError(f"Candidate is missing license overlay file: {entry['path']}")
        contents[entry["path"]] = file.read_bytes()
    return overlay["spec"], contents


def merge_three_way(path: str, current: bytes, base: bytes, licensed: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="pdfscore-license-merge-") as temp:
        files = []
        for name, value in (("current", current), ("base", base), ("licensed", licensed)):
            file = Path(temp) / name
            file.write_bytes(value)
            files.append(str(file))
        result = subprocess.run(
            ["git", "merge-file", "-p", *files],
            capture_output=True,
            env=isolated_environment(),
        )
    if result.returncode:
        raise ValueError(
            f"License changes conflict with newer develop changes in {path}; re-author them "
            "in a private license commit on the new source and derive again"
        )
    return result.stdout


def derive_overlay(
    repository: Path,
    destination: Path,
    base_commit: str,
    license_commit: str,
    source_commit: str,
    overlay_id: str,
) -> dict:
    """Seal the policy-approved license changes of ``license_commit`` for ``source_commit``.

    ``license_commit`` is either a private license commit on ``base_commit`` (first
    application) or the promoted main whose provenance names ``base_commit`` (maintenance).
    Changes to selected files are re-applied by a three-way merge onto the new source so
    newer develop changes are kept; any conflict fails closed.
    """
    repository, destination = repository.resolve(), destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Overlay destination already exists; use a fresh path")
    commits = [commit_id(repository, c) for c in (base_commit, license_commit, source_commit)]
    base, licensed, source = (source_files(repository, c) for c in commits)
    pinned_tool_hashes(repository, source)
    manifest = committed_manifest(repository, source)
    selected = set(selected_files(manifest))
    additions, modifications = overlay_policy(manifest)
    if not additions:
        raise ValueError("The source manifest declares no main license overlay policy")
    previous = previous_overlay(repository, licensed)
    if previous and previous["derived_from"]["source_commit"] != commits[0]:
        raise ValueError(
            "The promoted license commit was extracted from "
            f"{previous['derived_from']['source_commit']}; use it as --base-commit"
        )
    entries, contents, merged = [], {}, []
    for path in sorted(additions):
        value = committed_blob(repository, licensed, path)
        if value is not None:
            entries.append({"path": path, "operation": "add", "sha256": sha256(value)})
            contents[path] = value
    for path in sorted(modifications):
        old = committed_blob(repository, base, path)
        new = committed_blob(repository, licensed, path)
        if new == old:
            continue
        current = committed_blob(repository, source, path)
        if old is None or new is None or current is None:
            raise ValueError(f"License changes may modify, not add or remove, selected file {path}")
        if current != old:
            new = merge_three_way(path, current, old, new)
            merged.append(path)
        entries.append(
            {
                "path": path,
                "operation": "modify",
                "base_sha256": sha256(current),
                "sha256": sha256(new),
            }
        )
        contents[path] = new
    entries.sort(key=lambda entry: entry["path"])
    spec = {
        "schema_version": 1,
        "overlay_id": overlay_id,
        "derived_from": dict(
            zip(("base_commit", "license_commit", "source_commit"), commits, strict=True)
        ),
        "entries": entries,
    }
    overlay_changes(spec, manifest)
    if previous:
        dropped = {entry["path"] for entry in previous["entries"]} - set(contents)
        if dropped:
            raise ValueError(f"Derived overlay would drop main license material: {sorted(dropped)}")
    # Report, never apply, license-commit changes outside the policy (e.g. its own manifest edit).
    ignored = sorted(
        path
        for path in (set(base) | set(licensed)) - set(contents) - {PROVENANCE}
        if (
            path in selected
            and path in base
            and path in licensed
            and committed_blob(repository, base, path) != committed_blob(repository, licensed, path)
        )
        or (
            path not in selected
            and path in licensed
            and path not in base
            and (path in additions or path in LICENSE_NAMES or path.startswith("LICENSES/"))
        )
    )
    destination.mkdir(parents=True)
    (destination / OVERLAY_SPEC).write_bytes(canonical_json(spec))
    for path, value in contents.items():
        target = destination / OVERLAY_FILES / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return {
        "overlay_id": overlay_id,
        "spec_sha256": sha256(canonical_json(spec)),
        "derived_from": spec["derived_from"],
        "added": sorted(e["path"] for e in entries if e["operation"] == "add"),
        "modified": sorted(e["path"] for e in entries if e["operation"] == "modify"),
        "three_way_merged": merged,
        "license_commit_changes_not_applied": ignored,
    }


def write_snapshot(destination: Path, content: dict, provenance: dict) -> None:
    for path, value in content.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        target.chmod(0o755 if provenance["release"]["file_modes"].get(path) == "100755" else 0o644)


def commit_environment(provenance: dict) -> dict:
    env = isolated_environment()
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = "PDFScoreBar Release"
        env[f"GIT_{role}_EMAIL"] = "release@pdfscorebar.invalid"
        env[f"GIT_{role}_DATE"] = provenance["release"]["source_timestamp"] + " +0000"
    return env


def commit_message(provenance: dict) -> bytes:
    message = (
        f"Release candidate from {provenance['source_commit']}\n\n"
        f"Main parent: {provenance['release']['main_parent']}\n"
        f"Manifest SHA-256: {provenance['release']['manifest_sha256']}\n"
    )
    overlay = provenance["release"].get("main_overlay")
    if overlay:
        message += f"Main license overlay SHA-256: {overlay['spec_sha256']}\n"
    return message.encode()


def create_candidate(
    repository: Path,
    destination: Path,
    source_commit: str,
    main_commit: str,
    branch: str,
    license_overlay: Path | None = None,
) -> dict:
    repository, destination = repository.resolve(), destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Candidate destination already exists; use a fresh path")
    if destination.resolve().is_relative_to(repository):
        raise ValueError("Candidate must be outside the source checkout")
    if not branch.startswith("release/"):
        raise ValueError("Candidate branch must be versioned under release/")
    git(repository, "check-ref-format", "--branch", branch)
    overlay = load_overlay(license_overlay) if license_overlay else None
    content, provenance = snapshot(repository, source_commit, main_commit, overlay)
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
    return check_candidate(repository, destination, source_commit, main_commit, license_overlay)


def check_candidate(
    repository: Path,
    candidate: Path,
    source_commit: str,
    main_commit: str,
    license_overlay: Path | None = None,
) -> dict:
    """Re-derive the candidate from develop (plus its overlay) and compare every identity.

    Without ``license_overlay`` the overlay the candidate declares is re-validated against the
    develop selection and policy; pass the approved overlay to also bind its exact identity.
    """
    candidate = candidate.resolve()
    if Path(git(candidate, "rev-parse", "--show-toplevel").decode().strip()).resolve() != candidate:
        raise ValueError("Candidate must be the root of its own Git checkout")
    overlay = load_overlay(license_overlay) if license_overlay else candidate_overlay(candidate)
    content, expected = snapshot(repository, source_commit, main_commit, overlay)
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
    report = {
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
    overlay_record = expected["release"].get("main_overlay")
    if overlay_record:
        entries = overlay_record["spec"]["entries"]
        added = [e["path"] for e in entries if e["operation"] == "add"]
        report["license_overlay"] = {
            "overlay_id": overlay_record["spec"]["overlay_id"],
            "spec_sha256": overlay_record["spec_sha256"],
            "develop_selected_files": len(expected["files"]) - len(added),
            "added": added,
            "modified": [e["path"] for e in entries if e["operation"] == "modify"],
        }
    return report


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
            "--license-overlay",
            type=Path,
            help="Sealed main-only license overlay (from derive-overlay) applied to the extraction",
        )
        command.add_argument(
            "--report", type=Path, help="Write static evidence outside the candidate"
        )
        if name == "create":
            command.add_argument("--branch", required=True)
    derive = commands.add_parser(
        "derive-overlay", help="Seal policy-approved main-only license changes for a source"
    )
    derive.add_argument("destination", type=Path)
    derive.add_argument("--base-commit", required=True)
    derive.add_argument("--license-commit", required=True)
    derive.add_argument("--source-commit", required=True)
    derive.add_argument("--overlay-id", required=True)
    derive.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.report and args.report.resolve().is_relative_to(args.destination.resolve()):
            raise ValueError("Validation reports must stay outside the exact candidate tree")
        if args.command == "create":
            report = create_candidate(
                args.repository,
                args.destination,
                args.source_commit,
                args.main_commit,
                args.branch,
                args.license_overlay,
            )
        elif args.command == "check":
            report = check_candidate(
                args.repository,
                args.destination,
                args.source_commit,
                args.main_commit,
                args.license_overlay,
            )
        else:
            report = derive_overlay(
                args.repository,
                args.destination,
                args.base_commit,
                args.license_commit,
                args.source_commit,
                args.overlay_id,
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
