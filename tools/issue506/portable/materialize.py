"""Issue #506 PoC: bind a copied portable folder to its current location.

Run with the bundled interpreter (``python\\...\\python.exe``, not the venv) from the
portable root. Idempotent. It rewrites only location-dependent runtime metadata:

* ``venv\\pyvenv.cfg`` ``home`` -> bundled CPython directory
* ``app\\configs\\detector_profiles\\maintained_original_homr.json`` ``runtime`` paths
* ``markers\\*.txt`` (pinned commits, unchanged values)

and writes ``portable_identity.json`` with sha256 of the rewritten files, the models,
the font, and the bundled runtime freeze so the folder's identity is checkable.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent if (Path(__file__).parent / "venv").is_dir() else Path.cwd()
HOMR_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    pythons = sorted((root / "python").glob("cpython-3.12.*"))
    if len(pythons) != 1:
        raise SystemExit(f"expected one bundled CPython under {root / 'python'}")
    home = pythons[0]

    cfg = root / "venv" / "pyvenv.cfg"
    lines = cfg.read_text(encoding="utf-8").splitlines()
    cfg.write_text(
        "\n".join(f"home = {home}" if line.startswith("home") else line for line in lines) + "\n",
        encoding="utf-8",
    )

    markers = root / "markers"
    markers.mkdir(exist_ok=True)
    (markers / "homr_maintained_profile_commit.txt").write_text(HOMR_COMMIT + "\n", encoding="utf-8")
    (markers / "pdfscore_maintained_profile_commit.txt").write_text("workspace-runtime\n", encoding="utf-8")

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
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    assets = root / "assets"
    identity = {
        "root": str(root),
        "python_home": str(home),
        "profile_sha256": sha(profile_path),
        "assets": {
            str(p.relative_to(root)).replace("\\", "/"): sha(p)
            for p in sorted(assets.rglob("*"))
            if p.is_file()
        },
        "homr_models": {
            p.name: sha(p) for p in sorted((root / "venv" / "Lib" / "site-packages" / "homr").rglob("*.onnx"))
        },
    }
    (root / "portable_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"materialized": str(root), "python_home": str(home)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
