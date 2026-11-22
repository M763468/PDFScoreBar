"""Issue #553: rights/notice/source gate for the Windows portable folder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "portable_compliance", ROOT / "tools" / "licensing" / "portable_compliance.py"
)
pc = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = pc
spec.loader.exec_module(pc)

SP = "python/Lib/site-packages/"


def _policy(**overrides) -> dict:
    policy = {
        "schema_version": pc.POLICY_SCHEMA,
        "reviewed": {"date": "2026-11-23"},
        "components": {
            "permissive": {
                "title": "Permissive",
                "license": "MIT",
                "disposition": "cleared_with_notice",
                "notice_files": [SP + "*.dist-info/LICENSE*"],
            },
            "cpython": {
                "title": "CPython",
                "license": "PSF-2.0",
                "disposition": "cleared_with_notice",
                "notice_files": ["python/LICENSE.txt"],
            },
            "nvidia-unlisted": {
                "title": "NVIDIA unlisted",
                "license": "NVIDIA EULA",
                "disposition": "legal_interpretation_needed",
                "open_issue": "not in Attachment A",
            },
            "cuda": {
                "title": "CUDA redistributable",
                "license": "NVIDIA EULA",
                "disposition": "cleared_with_notice",
                "supplemental": [
                    {"name": "EULA", "file": "nvidia/eula.txt", "status": "collected"}
                ],
            },
            "weights": {
                "title": "Weights",
                "license": "first-party",
                "disposition": "cleared",
            },
        },
        "distributions": {"demo-pkg": {"version": "1.0", "component": "permissive"}},
        "file_rules": [
            {"pattern": SP + "demo/ptxas.exe", "component": "nvidia-unlisted"},
            {"pattern": SP + "demo/cudart64_12.dll", "component": "cuda"},
            {"pattern": "app/models/*.pth", "component": "weights", "sha256": None},
            {"pattern": SP + "*", "component": "permissive"},
            {"pattern": "python/*", "component": "cpython"},
        ],
    }
    policy.update(overrides)
    return policy


def _folder(tmp_path: Path, files: dict[str, bytes], distributions: dict[str, str]) -> Path:
    root = tmp_path / "PDFScoreBar"
    inventory = {}
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        inventory[rel] = [len(data), hashlib.sha256(data).hexdigest()]
    manifest = {
        "schema_version": pc.MANIFEST_SCHEMA,
        "application_source_commit": "a" * 40,
        "builder_source_commit": "a" * 40,
        "distributions": distributions,
        "files": inventory,
        "tree_digest": pc.tree_digest(inventory),
    }
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    (root / "runtime" / "build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


BASE_FILES = {
    "python/python312.dll": b"py",
    "python/LICENSE.txt": b"PSF license",
    SP + "demo/_native.pyd": b"pyd",
    SP + "demo/cudart64_12.dll": b"cudart",
    SP + "demo_pkg-1.0.dist-info/LICENSE": b"MIT text",
    "app/models/model.pth": b"weights",
    "app/src/main.py": b"print()",
}


def _write_policy(tmp_path: Path, policy: dict) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def _manifest(root: Path) -> Path:
    return root / "runtime" / "build_manifest.json"


def test_repository_policy_is_valid_and_reviews_every_pinned_distribution():
    policy = pc.load_policy(pc.DEFAULT_POLICY)
    lock = ROOT / "tools" / "windows_portable" / "requirements-cu126.txt"
    if lock.is_file():
        pins = {
            pc.canonical(name): version
            for name, version in (
                line.strip().split("==", 1)
                for line in lock.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            )
        }
        for name, version in pins.items():
            assert policy["distributions"][name]["version"] == version, name
    # Facts recorded in #553 must stay visible as blockers until they are resolved.
    components = policy["components"]
    assert components["nvidia-unlisted"]["disposition"] == "legal_interpretation_needed"
    assert components["barline-cnn-weights"]["disposition"] != "cleared"
    assert components["mmr-weights"]["disposition"] != "cleared"
    assert components["pdfscorebar-first-party"]["disposition"] == "permission_needed"
    unlisted = [r["pattern"] for r in policy["file_rules"] if r["component"] == "nvidia-unlisted"]
    assert any(p.endswith("ptxas.exe") for p in unlisted)
    assert any(p.endswith("nvperf_host.dll") for p in unlisted)


def test_repository_policy_routes_unlisted_nvidia_before_catch_all():
    policy = pc.load_policy(pc.DEFAULT_POLICY)
    rules = policy["file_rules"]
    hit = pc.match_rule(SP + "triton/backends/nvidia/bin/ptxas.exe", rules)
    assert hit["component"] == "nvidia-unlisted"
    hit = pc.match_rule(SP + "torch/lib/cublas64_12.dll", rules)
    assert hit["component"] == "nvidia-cuda-redistributable"
    hit = pc.match_rule(SP + "torch/lib/cudnn_ops64_9.dll", rules)
    assert hit["component"] == "nvidia-cudnn"
    hit = pc.match_rule(SP + "torch/lib/libiomp5md.dll", rules)
    assert hit["component"] == "intel-openmp"


def test_cleared_folder_passes_and_bundle_is_adjacent(tmp_path):
    policy = _policy()
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.0"})
    supplemental = tmp_path / "private"
    (supplemental / "nvidia").mkdir(parents=True)
    (supplemental / "nvidia" / "eula.txt").write_text("EULA", encoding="utf-8")
    policy_path = _write_policy(tmp_path, policy)
    assert pc.main(["check", str(_manifest(root)), "--policy", str(policy_path)]) == 0

    out = tmp_path / "PDFScoreBar-compliance"
    rc = pc.main(
        [
            "bundle",
            str(root),
            str(out),
            "--policy",
            str(policy_path),
            "--supplemental-dir",
            str(supplemental),
        ]
    )
    assert rc == 0
    report = json.loads((out / "COMPLIANCE_REPORT.json").read_text(encoding="utf-8"))
    assert report["handoff_ready"] is True
    raw = _manifest(root).read_bytes()
    assert report["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (out / "licenses" / "permissive" / SP / "demo_pkg-1.0.dist-info/LICENSE").is_file()
    assert (out / "supplemental" / "cuda" / "eula.txt").read_text(encoding="utf-8") == "EULA"
    sums = (out / "SHA256SUMS").read_text(encoding="utf-8")
    assert "THIRD_PARTY_NOTICES.md" in sums and "COMPLIANCE_REPORT.json" in sums
    # The portable folder itself is untouched by the bundle.
    assert not any("compliance" in p.name.lower() for p in root.rglob("*"))


def test_unlisted_nvidia_binary_blocks_handoff(tmp_path):
    files = dict(BASE_FILES, **{SP + "demo/ptxas.exe": b"ptxas"})
    root = _folder(tmp_path, files, {"demo-pkg": "1.0"})
    policy_path = _write_policy(tmp_path, _policy())
    report = tmp_path / "report.json"
    assert (
        pc.main(
            ["check", str(_manifest(root)), "--policy", str(policy_path), "--report", str(report)]
        )
        == 1
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["handoff_ready"] is False
    assert "nvidia-unlisted" in payload["blocked"]
    # Rehearsal mode reports the same blocker but does not fail.
    assert (
        pc.main(["check", str(_manifest(root)), "--policy", str(policy_path), "--allow-blocked"])
        == 0
    )


def test_unreviewed_native_file_or_distribution_is_an_error(tmp_path):
    policy = _policy(file_rules=[{"pattern": "python/*.dll", "component": "cpython"}])
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.0", "surprise": "2.0"})
    policy_path = _write_policy(tmp_path, policy)
    manifest, _ = pc.load_manifest(_manifest(root))
    ev = pc.evaluate(manifest, pc.load_policy(policy_path))
    assert any("surprise==2.0" in e for e in ev.errors)
    assert any(SP + "demo/_native.pyd" in e for e in ev.errors)
    assert any("app/models/model.pth" in e for e in ev.errors)
    assert (
        pc.main(["check", str(_manifest(root)), "--policy", str(policy_path), "--allow-blocked"])
        == 2
    )


def test_version_drift_and_model_hash_mismatch_fail_closed(tmp_path):
    policy = _policy()
    policy["file_rules"][2]["sha256"] = "0" * 64
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.1"})
    manifest, _ = pc.load_manifest(_manifest(root))
    ev = pc.evaluate(manifest, pc.load_policy(_write_policy(tmp_path, policy)))
    assert any("shipped 1.1, reviewed 1.0" in e for e in ev.errors)
    assert any("app/models/model.pth: sha256 differs" in e for e in ev.errors)


def test_pending_or_missing_supplemental_blocks(tmp_path):
    policy = _policy()
    policy["components"]["cuda"]["supplemental"][0]["status"] = "pending"
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.0"})
    manifest, _ = pc.load_manifest(_manifest(root))
    ev = pc.evaluate(manifest, pc.load_policy(_write_policy(tmp_path, policy)))
    assert ev.blocked == {"cuda": ["supplemental pending: EULA"]}

    # Collected in the policy but absent from the private directory: the bundle is blocked.
    policy_path = _write_policy(tmp_path, _policy())
    out = tmp_path / "bundle"
    rc = pc.main(["bundle", str(root), str(out), "--policy", str(policy_path)])
    assert rc == 1
    report = json.loads((out / "COMPLIANCE_REPORT.json").read_text(encoding="utf-8"))
    assert report["blocked"]["cuda"] == ["supplemental missing: nvidia/eula.txt"]


def test_tampered_folder_or_manifest_is_rejected(tmp_path):
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.0"})
    policy_path = _write_policy(tmp_path, _policy())
    (root / SP / "demo_pkg-1.0.dist-info/LICENSE").write_bytes(b"changed")
    with pytest.raises(SystemExit, match="differ from the build manifest"):
        pc.main(["bundle", str(root), str(tmp_path / "out"), "--policy", str(policy_path)])
    manifest = json.loads(_manifest(root).read_text(encoding="utf-8"))
    manifest["files"]["python/extra.dll"] = [1, "0" * 64]
    _manifest(root).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="tree digest"):
        pc.load_manifest(_manifest(root))


def test_bundle_refuses_to_write_inside_the_portable_folder(tmp_path):
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.0"})
    policy_path = _write_policy(tmp_path, _policy())
    with pytest.raises(SystemExit, match="adjacent"):
        pc.main(["bundle", str(root), str(root / "compliance"), "--policy", str(policy_path)])


def test_invalid_policy_is_rejected(tmp_path):
    policy = _policy()
    policy["components"]["weights"]["disposition"] = "owner_trained"
    with pytest.raises(ValueError, match="invalid disposition"):
        pc.load_policy(_write_policy(tmp_path, policy))
