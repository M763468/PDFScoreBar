#!/usr/bin/env python3
"""Validate the Issue #100 minimal-runtime extraction contract."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "MINIMAL_MAINLINE_SURFACE.json"


def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in proc.stdout.split(b"\0") if item]


def matches(files: list[str], pattern: str) -> list[str]:
    return [path for path in files if fnmatch.fnmatchcase(path, pattern)]


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = tracked_files()
    errors: list[str] = []

    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")

    runtime_entries = data.get("runtime_bundle_patterns", [])
    for entry in runtime_entries:
        pattern = entry["pattern"]
        if not matches(files, pattern):
            errors.append(f"runtime bundle pattern has no tracked matches: {pattern}")

    for section in (
        "development_validation_patterns",
        "development_tool_patterns",
        "reproduction_only_patterns",
    ):
        for entry in data.get(section, []):
            pattern = entry["pattern"]
            if not matches(files, pattern):
                errors.append(f"{section}: documented tracked pattern has no matches: {pattern}")
            if entry.get("include_in_runtime_bundle") is not False:
                errors.append(f"{section}: {pattern} must explicitly stay outside runtime bundle")

    for entry in data.get("current_repository_forbidden_patterns", []):
        pattern = entry["pattern"]
        found = matches(files, pattern)
        if found:
            preview = ", ".join(found[:5])
            suffix = "" if len(found) <= 5 else f" (+{len(found) - 5} more)"
            errors.append(f"forbidden tracked pattern present: {pattern}: {preview}{suffix}")

    for check in data.get("reference_checks", []):
        path = ROOT / check["path"]
        if not path.is_file():
            errors.append(f"reference-check file is missing: {check['path']}")
            continue
        text = path.read_text(encoding="utf-8")
        needle = check.get("contains")
        if needle and needle not in text:
            errors.append(f"{check['path']} does not reference {needle}")
        forbidden = check.get("not_contains")
        if forbidden and forbidden in text:
            errors.append(f"{check['path']} still references retired runtime path {forbidden}")

    if errors:
        print("Repository surface check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Repository surface check passed: "
        f"{len(runtime_entries)} runtime patterns, "
        f"{len(data.get('development_validation_patterns', []))} development-validation groups, "
        f"{len(data.get('reproduction_only_patterns', []))} reproduction-only groups, "
        f"{len(data.get('current_repository_forbidden_patterns', []))} forbidden-pattern guards."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
