#!/usr/bin/env python3
"""Validate the Issue #100 minimal-mainline repository-surface contract."""

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

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    for section in ("maintained_patterns", "runtime_exceptions", "retained_reproduction_patterns"):
        entries = data.get(section, [])
        for entry in entries:
            pattern = entry["pattern"]
            if not matches(files, pattern):
                errors.append(f"{section}: required tracked pattern has no matches: {pattern}")

    for entry in data.get("forbidden_patterns", []):
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
        needle = check["contains"]
        if needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{check['path']} does not reference {needle}")

    if errors:
        print("Repository surface check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    checked = (
        len(data.get("maintained_patterns", []))
        + len(data.get("runtime_exceptions", []))
        + len(data.get("retained_reproduction_patterns", []))
    )
    print(
        "Repository surface check passed: "
        f"{checked} required patterns, "
        f"{len(data.get('forbidden_patterns', []))} forbidden-pattern guards, "
        f"{len(data.get('reference_checks', []))} documentation references."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
