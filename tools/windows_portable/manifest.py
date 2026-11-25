"""File inventory and payload contract of a Windows portable folder (#535, #551).

Shared by the builder (writes ``runtime/build_manifest.json``) and the launcher
(``verify``). The inventory covers every file the runtime executes or loads: the
bundled CPython with its packages and native DLLs, the application (``app/``), the
launcher, the models/fonts and the profile markers. Byte-code caches are excluded
because Python creates them on first use.

Since #551 ``app/`` is exactly the main minimal distribution selected by
``docs/MINIMAL_MAINLINE_SURFACE.json`` (plus its ``DISTRIBUTION_PROVENANCE.json``), and
every other inventoried file belongs to an allowlisted Windows-only category recorded in
the manifest. ``verify`` checks both the inventory and that contract. Standard library
only: this module is shipped and runs under the bundled interpreter.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

MANIFEST_SCHEMA = "pdfscore.windows_portable.build_manifest.v2"
MANIFEST_PATH = Path("runtime") / "build_manifest.json"
APP_ROOT = "app"
LAUNCHER_ROOT = "launcher"
PYTHON_ROOT = "python"
ASSETS_ROOT = "assets"
MARKERS_ROOT = "runtime/markers"
INVENTORY_ROOTS = (PYTHON_ROOT, APP_ROOT, LAUNCHER_ROOT, ASSETS_ROOT, MARKERS_ROOT)
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


def selected_application(manifest_data: dict, sections: list[str]) -> set[str]:
    """Exact file entries of the given selection sections of the distribution manifest.

    ``sections`` is recorded at build time from the release selector, so the folder does
    not carry its own copy of the selection rules.
    """

    return {entry["pattern"] for section in sections for entry in manifest_data[section]}


def forbidden_matches(path: str, patterns: list[dict]) -> list[str]:
    hits = [entry["pattern"] for entry in patterns if fnmatch.fnmatchcase(path, entry["pattern"])]
    if any(part.lower() == ".git" for part in PurePosixPath(path).parts) and not hits:
        hits.append(".git")
    return hits


def check_contract(root: Path, manifest: dict, *, files: dict | None = None) -> list[str]:
    """Problems with the allowlisted payload structure recorded in ``manifest``.

    ``files`` defaults to the recorded inventory; the builder passes the fresh one.
    Hashes are compared between manifest sections; ``verify(full=True)`` re-hashes disk.
    """

    files = manifest["files"] if files is None else files
    problems: list[str] = []
    application = manifest["application"]
    overlay = manifest["windows_overlay"]
    if application["source_commit"] != manifest["source_commit"]:
        problems.append("application source commit differs from source_commit")

    # app/: exactly the main distribution and its provenance, byte for byte.
    prefix = APP_ROOT + "/"
    app_files = {
        name[len(prefix) :]: entry[1] for name, entry in files.items() if name.startswith(prefix)
    }
    expected_app = dict(application["files"])
    expected_app[application["provenance_path"]] = application["provenance_sha256"]
    for name in sorted(set(expected_app) - set(app_files)):
        problems.append(f"application file missing: {name}")
    for name in sorted(set(app_files) - set(expected_app)):
        problems.append(f"file outside the main application selection: app/{name}")
    for name in sorted(set(expected_app) & set(app_files)):
        if app_files[name] != expected_app[name]:
            problems.append(f"application file differs from the main selection: {name}")
    manifest_path = application["manifest_path"]
    if app_files.get(manifest_path) != application["manifest_sha256"]:
        problems.append("distribution manifest hash differs from the recorded selection")
    else:
        try:
            data = json.loads((root / APP_ROOT / manifest_path).read_text(encoding="utf-8"))
            if selected_application(data, application["selection_sections"]) != set(
                application["files"]
            ):
                problems.append("application file set differs from the shipped manifest selection")
        except (OSError, ValueError, KeyError, TypeError) as error:
            problems.append(f"cannot read the shipped distribution manifest: {error}")
    provenance = root / APP_ROOT / application["provenance_path"]
    try:
        recorded = json.loads(provenance.read_text(encoding="utf-8"))
        if (
            recorded.get("source_commit") != application["source_commit"]
            or recorded.get("files") != application["files"]
        ):
            problems.append("application provenance differs from the build manifest")
    except (OSError, ValueError, AttributeError) as error:
        problems.append(f"cannot read the application provenance: {error}")
    for name in sorted(app_files):
        hits = forbidden_matches(name, overlay["forbidden_payload_patterns"])
        if hits and name not in overlay.get("rights_pending_required", {}):
            problems.append(f"forbidden application file: {name} ({', '.join(hits)})")

    # Windows-only files: the allowlisted source files, generated roots and assets.
    listed = {entry["path"]: entry["sha256"] for entry in overlay["files"]}
    markers = next(
        (set(g.get("files", [])) for g in overlay["generated"] if g["path"] == MARKERS_ROOT), set()
    )
    assets = {entry["path"]: entry["sha256"] for entry in manifest["assets"]}
    for name, entry in sorted(files.items()):
        if name.startswith(prefix):
            continue
        top = name.split("/", 1)[0]
        if name in listed:
            if entry[1] != listed[name]:
                problems.append(f"Windows overlay file differs from its record: {name}")
        elif top == PYTHON_ROOT:
            continue
        elif top == ASSETS_ROOT and name in assets:
            if entry[1] != assets[name]:
                problems.append(f"asset differs from its record: {name}")
        elif name.startswith(MARKERS_ROOT + "/") and name[len(MARKERS_ROOT) + 1 :] in markers:
            continue
        else:
            problems.append(f"file outside the Windows allowlist: {name}")
    for name in sorted((set(listed) | set(assets)) - set(files)):
        problems.append(f"allowlisted Windows file missing: {name}")
    return problems


def verify(root: Path, *, full: bool) -> list[str]:
    """Return problems (empty when the folder matches its manifest).

    ``full`` hashes every file (minutes on a 6 GB folder); otherwise sizes and the
    presence of exactly the recorded files are checked. Both check the payload contract.
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
    problems += check_contract(root, manifest)
    return problems
