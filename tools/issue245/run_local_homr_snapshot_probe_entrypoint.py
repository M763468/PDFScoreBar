#!/usr/bin/env python3
"""Run the local HOMR probe with text-line-ending tolerant source checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.issue245 import run_local_homr_snapshot_probe as probe

_ORIGINAL_SHA256_FILE = probe.sha256_file
_TEXT_SOURCE_SUFFIXES = {".py", ".toml"}


def sha256_probe_file(path: Path) -> str:
    """Normalize CRLF only for archived text source in the probe build context."""
    if "build_context" in path.parts and path.suffix.lower() in _TEXT_SOURCE_SUFFIXES:
        normalized = path.read_bytes().replace(b"\r\n", b"\n")
        return hashlib.sha256(normalized).hexdigest()
    return _ORIGINAL_SHA256_FILE(path)


def main() -> int:
    probe.sha256_file = sha256_probe_file
    return probe.main()


if __name__ == "__main__":
    raise SystemExit(main())
