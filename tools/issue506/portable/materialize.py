"""Issue #506 PoC: bind a copied portable folder to its current location.

Run with the bundled interpreter (``python\\...\\python.exe``, not the venv) from the
portable root. Idempotent. It rewrites only location-dependent runtime metadata:

* ``venv\\pyvenv.cfg`` ``home`` -> bundled CPython directory
* ``app\\configs\\detector_profiles\\maintained_original_homr.json`` ``runtime`` paths
* ``markers\\*.txt`` (pinned commits, unchanged values)

and writes ``portable_identity.json``: a LIMITED, PoC-only identity record. It contains
sha256 of the rewritten profile, the assets (models, font), the HOMR ONNX files, the
bundled CPython version, a digest of the venv distribution list (name==version from
``*.dist-info/METADATA``, also written to ``portable_freeze.txt``), a digest of the
``app`` tree, and the source commit if the packager recorded one in
``app/SOURCE_COMMIT``.

It is NOT a runtime attestation: it is self-reported by the folder it describes, is not
signed, does not hash installed package files or native DLLs, and cannot prove that the
``app`` tree came from the recorded commit. A production build needs a reproducible
source/runtime ID plus a verification step (review of PR #531).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent if (Path(__file__).parent / "venv").is_dir() else Path.cwd()
HOMR_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"
NL = "\n"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def venv_freeze(site_packages: Path) -> list[str]:
    rows = []
    for meta in sorted(site_packages.glob("*.dist-info/METADATA")):
        text = meta.read_text(encoding="utf-8", errors="replace")
        name = re.search(r"^Name: (.+)$", text, re.M)
        version = re.search(r"^Version: (.+)$", text, re.M)
        rows.append(
            f"{name.group(1).strip() if name else meta.parent.name}=="
            f"{version.group(1).strip() if version else '?'}"
        )
    return sorted(rows, key=str.lower)


def tree_digest(root: Path, exclude: set[Path]) -> tuple[str, int]:
    """sha256 over sorted ``relative/path<TAB>sha256`` lines; ``__pycache__`` ignored."""
    lines = []
    for path in root.rglob("*"):
        if path.is_file() and path not in exclude and "__pycache__" not in path.parts:
            lines.append(path.relative_to(root).as_posix() + "\t" + sha(path))
    lines.sort()
    return hashlib.sha256((NL.join(lines) + NL).encode("utf-8")).hexdigest(), len(lines)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    pythons = sorted((root / "python").glob("cpython-3.12.*"))
    if len(pythons) != 1:
        raise SystemExit(f"expected one bundled CPython under {root / 'python'}")
    home = pythons[0]

    cfg = root / "venv" / "pyvenv.cfg"
    lines = cfg.read_text(encoding="utf-8").splitlines()
    cfg.write_text(
        NL.join(f"home = {home}" if line.startswith("home") else line for line in lines) + NL,
        encoding="utf-8",
    )

    markers = root / "markers"
    markers.mkdir(exist_ok=True)
    (markers / "homr_maintained_profile_commit.txt").write_text(HOMR_COMMIT + NL, encoding="utf-8")
    (markers / "pdfscore_maintained_profile_commit.txt").write_text("workspace-runtime" + NL, encoding="utf-8")

    app = root / "app"
    profile_path = app / "configs" / "detector_profiles" / "maintained_original_homr.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["runtime"] = {
        "python": str(root / "venv" / "Scripts" / "python.exe"),
        "homr_source": str(root / "venv" / "Lib" / "site-packages"),
        "pdfscore_source": str(app),
        "homr_commit_marker": str(markers / "homr_maintained_profile_commit.txt"),
        "pdfscore_commit_marker": str(markers / "pdfscore_maintained_profile_commit.txt"),
        "compat_entrypoint": str(app / "src" / "pipeline" / "detection" / "maintained_homr_worker.py"),
    }
    profile_path.write_text(json.dumps(profile, indent=2) + NL, encoding="utf-8")

    assets = root / "assets"
    site_packages = root / "venv" / "Lib" / "site-packages"
    freeze = venv_freeze(site_packages)
    freeze_text = NL.join(freeze) + NL
    source_marker = app / "SOURCE_COMMIT"
    app_digest, app_files = tree_digest(app, {profile_path, source_marker})
    identity = {
        "scope": "issue506-poc-limited-identity; not a runtime attestation (unsigned, self-reported)",
        "root": str(root),
        "python_home": str(home),
        "python_version": home.name,
        "source_commit": source_marker.read_text(encoding="utf-8").strip() if source_marker.is_file() else None,
        "app_tree_sha256": app_digest,
        "app_tree_files": app_files,
        "app_tree_excludes": ["configs/detector_profiles/maintained_original_homr.json", "SOURCE_COMMIT", "__pycache__"],
        "venv_freeze_sha256": hashlib.sha256(freeze_text.encode("utf-8")).hexdigest(),
        "venv_freeze_count": len(freeze),
        "profile_sha256": sha(profile_path),
        "assets": {
            str(p.relative_to(root)).replace("\\", "/"): sha(p)
            for p in sorted(assets.rglob("*"))
            if p.is_file()
        },
        "homr_models": {p.name: sha(p) for p in sorted((site_packages / "homr").rglob("*.onnx"))},
    }
    (root / "portable_freeze.txt").write_text(freeze_text, encoding="utf-8", newline="\n")
    (root / "portable_identity.json").write_text(json.dumps(identity, indent=2) + NL, encoding="utf-8")
    print(json.dumps({"materialized": str(root), "python_home": str(home)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
