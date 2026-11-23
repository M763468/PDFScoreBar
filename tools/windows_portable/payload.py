"""Pinned application and Windows overlay of the portable folder (#551). Builder-side only.

The portable ``app/`` is the main minimal distribution: the exact files selected from
``docs/MINIMAL_MAINLINE_SURFACE.json`` by ``tools/materialize_distribution.py`` read as
Git blobs of one frozen commit, plus the same ``DISTRIBUTION_PROVENANCE.json`` that
``materialize_distribution.py materialize`` writes for a clean checkout. The Windows-only
files are the allowlist of ``overlay.json`` (also read from the commit). Nothing else of
the source commit enters the folder.

Runs on any platform, so the payload can be assembled and audited without the Windows
runtime::

    python tools/windows_portable/payload.py stage <new-dir> --commit <40-hex sha> [--report r.json]

The staged directory holds only ``app/``, ``launcher/`` and ``PDFScoreBar.cmd``: no
interpreter, packages or assets (those are built on Windows by ``build_portable.py``).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import materialize_distribution  # noqa: E402
import release_candidate  # noqa: E402
from manifest import (  # noqa: E402
    APP_ROOT,
    LAUNCHER_ROOT,
    MARKERS_ROOT,
    forbidden_matches,
)
from materialize_distribution import (  # noqa: E402
    MANIFEST,
    PROVENANCE,
    SECTIONS,
    check_tree,
    selected_files,
)

OVERLAY_SPEC = "tools/windows_portable/overlay.json"
OVERLAY_SCHEMA = "pdfscore.windows_portable.overlay.v1"
LOCK = "tools/windows_portable/requirements-cu126.txt"
ASSETS = "tools/windows_portable/assets.json"
SELECTOR = "tools/materialize_distribution.py:selected_files"
GENERATED_ROOTS = ("python", "assets", MARKERS_ROOT)
TRANSFORMS = ("copy", "crlf-ascii")
# Running builder modules; each must equal its blob in the frozen commit.
BUILDER_MODULES = {
    "tools/windows_portable/build_portable.py": HERE / "build_portable.py",
    "tools/windows_portable/payload.py": HERE / "payload.py",
    "tools/windows_portable/manifest.py": HERE / "manifest.py",
    "tools/windows_portable/user_setup.py": HERE / "user_setup.py",
    "tools/materialize_distribution.py": Path(materialize_distribution.__file__),
    "tools/release_candidate.py": Path(release_candidate.__file__),
}
# Repository-relative runtime file references in shipped code/configuration.
PATH_REFERENCE = re.compile(
    r"(?<![\w/.-])((?:configs|models|src|docker|tools)/[\w./-]+\.(?:py|ya?ml|json|pth|onnx|pt))"
)
MODULE_REFERENCE = re.compile(r"(?:src|tools|docker)(?:\.[A-Za-z_]\w*)+")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(data: bytes, kind: str) -> bytes:
    if kind == "copy":
        return data
    if kind == "crlf-ascii":
        return ("\r\n".join(data.decode("ascii").splitlines()) + "\r\n").encode("ascii")
    raise ValueError(f"Unknown overlay transform: {kind}")


@dataclass
class Snapshot:
    commit: str
    tree: str
    manifest_data: dict
    app: dict[str, bytes]
    spec: dict
    overlay: dict[str, bytes]
    overlay_records: list[dict]
    inputs: dict[str, bytes]
    builder: dict[str, bytes]

    @property
    def selected(self) -> list[str]:
        return sorted(path for path in self.app if path != PROVENANCE)

    def application_record(self) -> dict:
        return {
            "root": APP_ROOT,
            "source_commit": self.commit,
            "source_tree": self.tree,
            "manifest_path": MANIFEST,
            "manifest_sha256": sha256(self.app[MANIFEST]),
            "manifest_schema_version": self.manifest_data["schema_version"],
            "selector": SELECTOR,
            "selector_sha256": sha256(self.builder["tools/materialize_distribution.py"]),
            "selection_sections": list(SECTIONS),
            "provenance_path": PROVENANCE,
            "provenance_sha256": sha256(self.app[PROVENANCE]),
            "file_count": len(self.selected),
            "files": {path: sha256(self.app[path]) for path in self.selected},
        }

    def overlay_record(self) -> dict:
        spec = self.spec
        return {
            "spec_path": OVERLAY_SPEC,
            "spec_sha256": sha256(self.inputs[OVERLAY_SPEC]),
            "files": self.overlay_records,
            "generated": spec["generated"],
            "build_inputs": {
                path: {"sha256": sha256(self.inputs[path]), "reason": reason}
                for path, reason in sorted(spec["build_inputs"].items())
            },
            "build_time_application_scripts": spec["build_time_application_scripts"],
            "common_inactive_on_windows": spec["common_inactive_on_windows"],
            "rights_pending_required": spec["rights_pending_required"],
            "forbidden_payload_patterns": spec["forbidden_payload_patterns"],
        }


def _blob(repository: Path, entries: dict, path: str) -> bytes:
    mode, oid = entries.get(path, (None, None))
    if mode not in {"100644", "100755"}:
        raise ValueError(f"Missing or unsafe pinned source file: {path}")
    return release_candidate.git(repository, "cat-file", "blob", oid)


def _valid_destination(path: str) -> bool:
    pure = PurePosixPath(path)
    return str(pure) == path and (
        path == "PDFScoreBar.cmd"
        or (len(pure.parts) == 2 and pure.parts[0] == LAUNCHER_ROOT and pure.suffix == ".py")
    )


def validate_spec(spec: dict, selected: set[str], tracked: set[str]) -> None:
    """Fail closed on any allowlist entry outside the Windows-only contract."""

    errors = []
    if spec.get("schema_version") != OVERLAY_SCHEMA:
        errors.append(f"Unsupported overlay schema: {spec.get('schema_version')}")
    application = spec.get("application", {})
    if application != {
        "root": APP_ROOT,
        "manifest": MANIFEST,
        "selector": SELECTOR,
        "provenance": PROVENANCE,
    }:
        errors.append(
            f"Overlay application contract differs from the release selector: {application}"
        )
    destinations = set()
    for entry in spec.get("source_files", []):
        source, path = entry.get("source", ""), entry.get("path", "")
        if (
            not source.startswith("tools/windows_portable/")
            or source not in tracked
            or source in selected
            or source in spec.get("build_inputs", {})
        ):
            errors.append(f"Invalid Windows overlay source: {source}")
        if not _valid_destination(path) or path in destinations:
            errors.append(f"Invalid or duplicate Windows overlay destination: {path}")
        if entry.get("transform") not in TRANSFORMS or not entry.get("reason"):
            errors.append(f"Overlay entry needs a known transform and a reason: {entry}")
        destinations.add(path)
    generated = [entry.get("path") for entry in spec.get("generated", [])]
    if sorted(generated) != sorted(GENERATED_ROOTS) or not all(
        entry.get("reason") and entry.get("verified_by") for entry in spec["generated"]
    ):
        errors.append(f"Generated Windows roots must be exactly {GENERATED_ROOTS} with reasons")
    inputs = spec.get("build_inputs", {})
    for path in {LOCK, ASSETS, OVERLAY_SPEC} | set(BUILDER_MODULES) - {
        "tools/windows_portable/manifest.py",
        "tools/windows_portable/user_setup.py",
    }:
        if path not in inputs:
            errors.append(f"Build input is not recorded: {path}")
    for path, reason in inputs.items():
        if path not in tracked or path in selected or not reason:
            errors.append(f"Invalid build input: {path}")
    for section in (
        "build_time_application_scripts",
        "common_inactive_on_windows",
        "rights_pending_required",
    ):
        for path, reason in spec.get(section, {}).items():
            if path not in selected or not reason:
                errors.append(f"{section} must name selected application files: {path}")
    patterns = spec.get("forbidden_payload_patterns", [])
    if not patterns or not all(e.get("pattern") and e.get("reason") for e in patterns):
        errors.append("Forbidden payload patterns need a pattern and a reason")
    for path in sorted(selected):
        hits = forbidden_matches(path, patterns)
        if hits and path not in spec.get("rights_pending_required", {}):
            errors.append(f"Selected application file matches a forbidden pattern: {path} {hits}")
    if errors:
        raise ValueError("Windows overlay check failed:\n" + "\n".join(errors))


def snapshot(repository: Path, commit: str) -> Snapshot:
    """Read the application, overlay and build inputs from one frozen commit."""

    repository = repository.resolve()
    commit = release_candidate.commit_id(repository, commit)
    entries = release_candidate.source_files(repository, commit)
    manifest_data = json.loads(_blob(repository, entries, MANIFEST))
    if manifest_data.get("schema_version") != 3:
        raise ValueError("Unsupported distribution manifest schema; expected version 3")
    paths = selected_files(manifest_data)
    if MANIFEST not in paths:
        raise ValueError("The distribution must include its own manifest")
    app = {path: _blob(repository, entries, path) for path in paths}
    provenance = {
        "schema_version": 1,
        "source_commit": commit,
        "source_branch": "detached",
        "source_dirty": False,
        "files": {path: sha256(app[path]) for path in paths},
    }
    # Same bytes as materialize_distribution.materialize() of a clean detached checkout.
    app[PROVENANCE] = (json.dumps(provenance, indent=2) + "\n").encode("utf-8")
    spec_bytes = _blob(repository, entries, OVERLAY_SPEC)
    spec = json.loads(spec_bytes)
    validate_spec(spec, set(paths), set(entries))
    overlay, records = {}, []
    for entry in spec["source_files"]:
        source = _blob(repository, entries, entry["source"])
        data = transform(source, entry["transform"])
        overlay[entry["path"]] = data
        records.append(
            {
                "path": entry["path"],
                "source": entry["source"],
                "source_sha256": sha256(source),
                "sha256": sha256(data),
                "transform": entry["transform"],
                "reason": entry["reason"],
            }
        )
    inputs = {path: _blob(repository, entries, path) for path in spec["build_inputs"]}
    builder = {path: _blob(repository, entries, path) for path in BUILDER_MODULES}
    tree = release_candidate.git(repository, "rev-parse", commit + "^{tree}").decode().strip()
    result = Snapshot(commit, tree, manifest_data, app, spec, overlay, records, inputs, builder)
    errors = runtime_reference_problems(result)
    if errors:
        raise ValueError("Application reference check failed:\n" + "\n".join(errors))
    return result


def check_running_builder(snap: Snapshot) -> dict[str, str]:
    """Require the running builder to be the frozen commit's builder (fail closed).

    Line endings are normalized so a Windows checkout with ``core.autocrlf`` passes.
    """

    hashes = {}
    for path, running in BUILDER_MODULES.items():
        pinned = snap.builder[path]
        if running.read_bytes().replace(b"\r\n", b"\n") != pinned.replace(b"\r\n", b"\n"):
            raise ValueError(
                f"Running builder file differs from the pinned commit: {path}; "
                "run the builder from a clean checkout of --commit"
            )
        hashes[path] = sha256(pinned)
    return hashes


def _optional_references(data: dict) -> dict[str, set[str]]:
    optional: dict[str, set[str]] = {}
    for section in ("runtime_optional_source_imports", "runtime_optional_module_references"):
        for importer, targets in data.get(section, {}).items():
            optional.setdefault(importer, set()).update(targets)
    return optional


def _module_targets(module: str) -> set[str]:
    base = module.replace(".", "/")
    parts = base.split("/")
    return {base + ".py", base + "/__init__.py"} | {
        "/".join(parts[:i]) + ".py" for i in range(1, len(parts))
    }


def _app_path_chains(tree: ast.AST) -> set[str]:
    """``APP / "a" / "b.py"`` expressions in the launcher, as ``a/b.py``."""

    chains = set()
    for node in ast.walk(tree):
        parts = []
        while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
                break
            parts.insert(0, node.right.value)
            node = node.left
        else:
            if isinstance(node, ast.Name) and node.id == "APP" and parts:
                chains.add("/".join(parts))
    return chains


def runtime_reference_problems(snap: Snapshot) -> list[str]:
    """Shipped code/config/model references and launcher entry points must be in ``app/``.

    Complements ``check_tree`` (imports and document/UI links): repository-relative
    config/model/source paths named by selected files, ``weights``/``implementation`` of
    the model manifests, the launcher's ``-m`` modules and ``APP`` paths, and the
    application scripts the builder runs.
    """

    app = set(snap.app)
    optional = _optional_references(snap.manifest_data)
    problems = []
    for path in snap.selected:
        data = snap.app[path]
        found: set[str] = set()
        if path.endswith(".py"):
            for node in ast.walk(ast.parse(data.decode("utf-8"), filename=path)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    found.update(PATH_REFERENCE.findall(node.value))
        elif path.startswith("configs/") and path.endswith((".yaml", ".yml", ".json")):
            found.update(PATH_REFERENCE.findall(data.decode("utf-8")))
        elif path.startswith("models/") and path.endswith("/manifest.json"):
            model = json.loads(data)
            found.update(
                value
                for key in ("weights", "implementation")
                for section in (model, model.get("architecture"))
                if isinstance(section, dict)
                for value in [section.get(key)]
                if isinstance(value, str)
            )
        for target in sorted(found):
            if target not in app and target not in optional.get(path, set()):
                problems.append(f"Unshipped runtime reference: {path} -> {target}")
    for entry in snap.overlay_records:
        if not entry["path"].endswith(".py"):
            continue
        tree = ast.parse(snap.overlay[entry["path"]].decode("utf-8"), filename=entry["path"])
        targets = set(_app_path_chains(tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if MODULE_REFERENCE.fullmatch(node.value):
                    if not _module_targets(node.value) & app:
                        problems.append(
                            f"Launcher module is not in the application: {entry['path']} -> {node.value}"
                        )
        directories = {
            "/".join(PurePosixPath(p).parts[:i])
            for p in app
            for i in range(1, len(PurePosixPath(p).parts))
        }
        for target in sorted(targets - app - directories):
            problems.append(f"Launcher path is not in the application: {entry['path']} -> {target}")
    for script in snap.spec["build_time_application_scripts"]:
        if script not in app:
            problems.append(f"Build-time application script is not shipped: {script}")
    cmd = snap.overlay.get("PDFScoreBar.cmd", b"").decode("ascii")
    for entry in snap.overlay_records:
        if entry["path"] == f"{LAUNCHER_ROOT}/launcher.py" and (
            f"{LAUNCHER_ROOT}\\launcher.py" not in cmd
        ):
            problems.append("PDFScoreBar.cmd does not start launcher\\launcher.py")
    return problems


def stage(snap: Snapshot, root: Path) -> None:
    """Write ``app/`` and the source overlay into ``root`` and check the isolated tree."""

    files = [(f"{APP_ROOT}/{path}", data) for path, data in snap.app.items()]
    for relative, data in [*files, *snap.overlay.items()]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    errors = check_tree(root / APP_ROOT)
    if errors:
        raise ValueError("Application check failed:\n" + "\n".join(errors))


def static_report(snap: Snapshot) -> dict:
    return {
        "schema_version": "pdfscore.windows_portable.static_payload.v1",
        "source_commit": snap.commit,
        "source_tree": snap.tree,
        "application": snap.application_record(),
        "windows_overlay": snap.overlay_record(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=HERE.parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    staged = commands.add_parser("stage", help="assemble app/ + launcher overlay (no runtime)")
    staged.add_argument("destination", type=Path)
    staged.add_argument("--commit", required=True, help="frozen 40-hex source commit")
    staged.add_argument("--report", type=Path, help="JSON report outside the destination")
    args = parser.parse_args()
    try:
        destination = args.destination.absolute()
        if destination.exists():
            raise ValueError("Destination must be a fresh path")
        if args.report and args.report.absolute().is_relative_to(destination):
            raise ValueError("Write the report outside the staged payload")
        snap = snapshot(args.repository, args.commit)
        builder_files = check_running_builder(snap)
        destination.mkdir(parents=True)
        stage(snap, destination)
        report = static_report(snap)
        report["builder_source_commit"] = snap.commit
        report["builder_files"] = builder_files
        report["staged_files"] = sorted(
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            f"Staged {report['application']['file_count']} application files + provenance and "
            f"{len(snap.overlay)} Windows overlay files from {snap.commit}"
        )
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
