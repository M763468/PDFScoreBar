#!/usr/bin/env python3
"""Materialize and check the exact Issue #409 release candidate, without Git in the result."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "docs/MINIMAL_MAINLINE_SURFACE.json"
PROVENANCE = "DISTRIBUTION_PROVENANCE.json"
SECTIONS = (
    "runtime_bundle_patterns",
    "distribution_support_patterns",
    "distribution_metadata_patterns",
)


OVERLAY_POLICY = "main_license_overlay_policy"
OVERLAY_KEYS = {"schema_version", "overlay_id", "derived_from", "entries"}
SHA256 = re.compile(r"[0-9a-f]{64}")


def exact_path(path: object) -> bool:
    if not isinstance(path, str):
        return False
    pure = PurePosixPath(path)
    return not (
        pure.is_absolute()
        or ".." in pure.parts
        or str(pure) != path
        or any(c in path for c in "*?[")
        or any(part.lower() == ".git" for part in pure.parts)
        or path == PROVENANCE
    )


def selected_files(data: dict) -> list[str]:
    paths = []
    for section in SECTIONS:
        for entry in data[section]:
            path = entry["pattern"]
            if not exact_path(path) or not entry.get("role"):
                raise ValueError(f"Invalid exact distribution entry: {entry}")
            paths.append(path)
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate distribution file")
    return sorted(paths)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def overlay_policy(data: dict) -> tuple[dict[str, bool], set[str]]:
    """Main-only license additions (path -> required) and selected files they may modify.

    The policy names paths only; the license material itself never lives on develop.
    """
    policy = data.get(OVERLAY_POLICY)
    if policy is None:
        return {}, set()
    selected = set(selected_files(data))
    additions: dict[str, bool] = {}
    modifications: set[str] = set()
    for entry in policy["additions"]:
        path = entry.get("pattern")
        if (
            not exact_path(path)
            or not entry.get("role")
            or path in selected
            or path in additions
            or not isinstance(entry.get("required", False), bool)
        ):
            raise ValueError(f"Invalid main license overlay addition: {entry}")
        additions[path] = entry.get("required", False)
    for entry in policy["modifications"]:
        path = entry.get("pattern")
        if (
            path not in selected
            or path == MANIFEST
            or not entry.get("role")
            or path in modifications
        ):
            raise ValueError(f"Invalid main license overlay modification: {entry}")
        modifications.add(path)
    if not any(additions.values()):
        raise ValueError("The main license overlay policy must require at least one file")
    return additions, modifications


def overlay_changes(spec: dict, data: dict) -> tuple[set[str], set[str]]:
    """Validate a main license overlay against the manifest policy; return (added, modified)."""
    additions, modifications = overlay_policy(data)
    if not additions:
        raise ValueError("The distribution manifest declares no main license overlay policy")
    if not isinstance(spec, dict) or set(spec) != OVERLAY_KEYS or spec["schema_version"] != 1:
        raise ValueError("Unsupported main license overlay; expected schema version 1")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", str(spec["overlay_id"])):
        raise ValueError("Invalid main license overlay id")
    derived = spec["derived_from"]
    if (
        not isinstance(derived, dict)
        or set(derived) != {"base_commit", "license_commit", "source_commit"}
        or not all(re.fullmatch(r"[0-9a-f]{40}", str(v)) for v in derived.values())
    ):
        raise ValueError("Main license overlay must record its frozen derivation commits")
    entries = spec["entries"]
    paths = [entry.get("path") if isinstance(entry, dict) else None for entry in entries or []]
    if not paths or not all(exact_path(p) for p in paths) or paths != sorted(set(paths)):
        raise ValueError("Main license overlay entries must be unique, sorted exact paths")
    added, modified = set(), set()
    for entry in entries:
        path, operation = entry["path"], entry.get("operation")
        keys = {"path", "operation", "sha256"} | (
            {"base_sha256"} if operation == "modify" else set()
        )
        if set(entry) != keys or not all(
            SHA256.fullmatch(str(entry[k])) for k in keys & {"sha256", "base_sha256"}
        ):
            raise ValueError(f"Invalid main license overlay entry: {entry}")
        if operation == "add" and path in additions:
            added.add(path)
        elif operation == "modify" and path in modifications:
            modified.add(path)
        else:
            raise ValueError(f"Main license overlay entry is outside the approved policy: {path}")
    missing = {path for path, required in additions.items() if required} - added
    if missing:
        raise ValueError(
            f"Main license overlay omits required main license files: {sorted(missing)}"
        )
    return added, modified


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_tree(
    root: Path, *, verify_provenance: bool = True, git_checkout: bool = False
) -> list[str]:
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    selected = set(selected_files(data))
    errors = []
    provenance_path = root / PROVENANCE
    provenance = None
    overlay_hashes: dict[str, str] = {}
    if verify_provenance and provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        overlay = provenance.get("release", {}).get("main_overlay")
        if overlay is not None:
            try:
                spec = overlay["spec"]
                if overlay.get("spec_sha256") != hashlib.sha256(canonical_json(spec)).hexdigest():
                    errors.append("Main license overlay identity differs from its recorded spec")
                added, _ = overlay_changes(spec, data)
                selected |= added
                overlay_hashes = {entry["path"]: entry["sha256"] for entry in spec["entries"]}
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                errors.append(f"Invalid main license overlay: {exc}")
    for path in selected:
        file = root / path
        if (
            not file.is_file()
            or file.is_symlink()
            or not file.resolve().is_relative_to(root.resolve())
        ):
            errors.append(f"Missing or unsafe distribution file: {path}")
    known = selected | set(data["source_excluded"])
    optional = {k: dict(v) for k, v in data["runtime_optional_source_imports"].items()}
    for importer, targets in data.get("runtime_optional_module_references", {}).items():
        optional.setdefault(importer, {}).update(targets)
    for path in sorted(selected):
        file = root / path
        if file.suffix == ".py" and file.is_file():
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=path)
            package = str(Path(path).parent).replace("/", ".")
            modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    name = node.module or ""
                    if node.level:
                        name = importlib.util.resolve_name("." * node.level + name, package)
                    modules.add(name)
                    modules.update(f"{name}.{a.name}" for a in node.names)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # Production workers launch local modules in subprocesses.
                    if re.fullmatch(r"(?:src|tools|docker)(?:\.[A-Za-z_]\w*)+", node.value):
                        modules.add(node.value)
            for module in modules:
                if module.split(".")[0] not in {"src", "tools", "docker"}:
                    continue
                base = module.replace(".", "/")
                parts = base.split("/")
                targets = {base + ".py"} | {
                    "/".join(parts[:i]) + "/__init__.py" for i in range(1, len(parts) + 1)
                }
                for target in targets & known:
                    if target not in selected and target not in optional.get(path, {}):
                        errors.append(f"Undeclared local dependency: {path} -> {target}")
                # A local module may be absent from both manifest and isolated disk.
                # Attribute imports are handled via their known parent module.
                if (
                    not any(t in known for t in targets)
                    and not any("/".join(parts[:i]) + ".py" in known for i in range(1, len(parts)))
                    and not any(p.startswith(base + "/") for p in known)
                ):
                    errors.append(f"Unknown local module reference: {path} -> {module}")
        if file.suffix in {".md", ".html", ".js"} and file.is_file():
            text = file.read_text(encoding="utf-8")
            refs = (
                re.findall(r"\]\(([^)]+)\)", text)
                if file.suffix == ".md"
                else re.findall(r'(?:src=["\']|from\s*["\'])([^"\']+)', text)
            )
            for ref in refs:
                if ref.startswith(("http:", "https:", "#", "data:")):
                    continue
                target = file.parent / ref.split("#")[0]
                if not target.exists() or not target.resolve().is_relative_to(root.resolve()):
                    errors.append(f"Missing local document/UI reference: {path} -> {ref}")
    if verify_provenance:
        if provenance is None:
            errors.append("Distribution provenance is missing")
        else:
            hashes = provenance.get("files", {})
            if set(hashes) != selected:
                errors.append("Provenance file selection differs from manifest")
            for path, expected in overlay_hashes.items():
                if hashes.get(path) != expected:
                    errors.append(f"Main license overlay hash differs from provenance: {path}")
            for path, expected in hashes.items():
                if path in selected and (
                    not (root / path).is_file() or digest(root / path) != expected
                ):
                    errors.append(f"Distribution content hash mismatch: {path}")
            actual = set()
            for directory, dirs, files in os.walk(root, followlinks=False):
                parent = Path(directory)
                if git_checkout and parent == root:
                    dirs[:] = [name for name in dirs if name != ".git"]
                    files = [name for name in files if name != ".git"]
                for name in dirs + files:
                    path = parent / name
                    if path.is_symlink():
                        errors.append(f"Unsafe candidate symlink: {path.relative_to(root)}")
                dirs[:] = [name for name in dirs if name != "__pycache__"]
                actual.update((parent / name).relative_to(root).as_posix() for name in files)
            if actual != selected | {PROVENANCE}:
                errors.append(
                    f"Unexpected candidate files: {sorted(actual - selected - {PROVENANCE})}"
                )
    return errors


def materialize(source: Path, destination: Path) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Candidate must be outside the source checkout")
    if destination.exists():
        raise ValueError("Candidate destination already exists; use a fresh path")
    data = json.loads((source / MANIFEST).read_text(encoding="utf-8"))
    paths = selected_files(data)
    # Validate every source before creating a partial candidate.
    for path in paths:
        file = source / path
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(source):
            raise ValueError(f"Missing or unsafe source file: {path}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=source, text=True
    ).strip()
    provenance = {
        "schema_version": 1,
        "source_commit": commit,
        "source_branch": branch or "detached",
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
        ),
        "files": {p: digest(source / p) for p in paths},
    }
    destination.mkdir(parents=True)
    for path in paths:
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, target)
    (destination / PROVENANCE).write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    errors = check_tree(destination)
    if errors:
        raise ValueError("Candidate check failed:\n" + "\n".join(errors))
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("materialize")
    build.add_argument("destination", type=Path)
    build.add_argument("--source", type=Path, default=ROOT)
    check = commands.add_parser("check")
    check.add_argument("root", type=Path)
    check.add_argument("--git-checkout", action="store_true", help="Exclude only root Git metadata")
    args = parser.parse_args()
    try:
        if args.command == "materialize":
            result = materialize(args.source, args.destination)
            print(
                f"Materialized {len(result['files'])} files from {result['source_commit']} (dirty={result['source_dirty']})"
            )
        else:
            errors = check_tree(args.root.resolve(), git_checkout=args.git_checkout)
            if errors:
                raise ValueError("\n".join(errors))
            print("Isolated distribution dependency/reference/content check passed")
    except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
