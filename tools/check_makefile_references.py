#!/usr/bin/env python3
"""Check literal repository file references used by Makefile recipes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PATH = re.compile(
    r"(?<![\w$])(?:\./)?(?:scripts|tools|src|configs|tests|\.agents/skills)/"
    r"[A-Za-z0-9_./*?-]+"
)


def recipe_references(makefile: Path) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    current_targets: list[str] = []

    for line in makefile.read_text(encoding="utf-8").splitlines():
        if line.startswith("\t"):
            for reference in REPOSITORY_PATH.findall(line):
                references.extend((target, reference) for target in current_targets)
            continue

        current_targets = []
        if line and not line[0].isspace() and ":" in line and not line.startswith("#"):
            lhs = line.split(":", 1)[0]
            current_targets = [item for item in lhs.split() if item]

    return references


def main() -> int:
    makefiles = [ROOT / "Makefile", ROOT / "tools/issue120/Makefile.stage_e.mk"]
    missing: set[tuple[str, str]] = set()

    for makefile in makefiles:
        for target, reference in recipe_references(makefile):
            candidate = ROOT / reference.removeprefix("./")
            if any(char in reference for char in "*?"):
                if not list(ROOT.glob(reference.removeprefix("./"))):
                    missing.add((target, reference))
            elif not candidate.exists():
                missing.add((target, reference))

    if missing:
        for target, reference in sorted(missing):
            print(f"{target}: missing repository reference {reference}", file=sys.stderr)
        return 1

    print("Makefile recipe references resolve to repository files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
