"""File inventory of a Windows portable folder (#535).

Shared by the builder (writes ``runtime/build_manifest.json``) and the launcher
(``verify``). The inventory covers every file the runtime executes or loads: the
bundled CPython with its packages and native DLLs, the application source, the
models/fonts and the profile markers. Byte-code caches are excluded because Python
creates them on first use.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

MANIFEST_SCHEMA = "pdfscore.windows_portable.build_manifest.v1"
MANIFEST_PATH = Path("runtime") / "build_manifest.json"
INVENTORY_ROOTS = ("python", "app", "assets", "runtime/markers")
INVENTORY_FILES = ("PDFScoreBar.cmd",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    return "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}


def inventory_paths(root: Path) -> Iterable[Path]:
    for name in INVENTORY_FILES:
        path = root / name
        if path.is_file():
            yield path
    for name in INVENTORY_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not _excluded(path.relative_to(root)):
                yield path


def build_inventory(root: Path) -> dict[str, list]:
    """``{posix_relative_path: [size, sha256]}`` for every inventoried file."""
    return {
        path.relative_to(root).as_posix(): [path.stat().st_size, sha256_file(path)]
        for path in inventory_paths(root)
    }


def tree_digest(files: dict[str, list]) -> str:
    lines = "".join(f"{name}\t{size}\t{digest}\n" for name, (size, digest) in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def load_manifest(root: Path) -> dict:
    payload = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    if payload.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported portable manifest: {payload.get('schema_version')}")
    if tree_digest(payload["files"]) != payload["tree_digest"]:
        raise ValueError("Portable manifest file list does not match its tree digest")
    return payload


def verify(root: Path, *, full: bool) -> list[str]:
    """Return problems (empty when the folder matches its manifest).

    ``full`` hashes every file (minutes on a 6 GB folder); otherwise sizes and the
    presence of exactly the recorded files are checked.
    """

    manifest = load_manifest(root)
    expected: dict[str, list] = manifest["files"]
    problems: list[str] = []
    actual = {path.relative_to(root).as_posix(): path for path in inventory_paths(root)}
    for name in sorted(set(expected) - set(actual)):
        problems.append(f"missing: {name}")
    for name in sorted(set(actual) - set(expected)):
        problems.append(f"unexpected: {name}")
    for name in sorted(set(expected) & set(actual)):
        size, digest = expected[name]
        path = actual[name]
        if path.stat().st_size != size:
            problems.append(f"size mismatch: {name}")
        elif full and sha256_file(path) != digest:
            problems.append(f"sha256 mismatch: {name}")
    return problems
