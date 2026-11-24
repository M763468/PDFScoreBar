"""Issue #533: production runtime without non-commercial SR code or HOMR transformer weights."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "src" / "third_party" / "realesrgan_sr"
EXCLUDED = ("basicsr", "realesrgan", "gfpgan", "facexlib")


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_production_sources_do_not_import_excluded_sr_distributions() -> None:
    offenders = []
    for base in ("src", "docker"):
        for path in sorted((ROOT / base).rglob("*.py")):
            hits = _imported_roots(path).intersection(EXCLUDED)
            if hits:
                offenders.append(f"{path.relative_to(ROOT)}: {sorted(hits)}")
    assert offenders == []


def test_vendored_sr_package_keeps_upstream_licenses_and_modification_notices() -> None:
    assert "Apache License" in (VENDORED / "LICENSE-BasicSR.txt").read_text(encoding="utf-8")
    assert "BSD 3-Clause" in (VENDORED / "LICENSE-Real-ESRGAN.txt").read_text(encoding="utf-8")
    rrdbnet = (VENDORED / "rrdbnet.py").read_text(encoding="utf-8")
    upsampler = (VENDORED / "upsampler.py").read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: Apache-2.0" in rrdbnet
    assert "Modifications by PDFScoreBar contributors" in rrdbnet
    assert "SPDX-License-Identifier: BSD-3-Clause" in upsampler
    assert "a4abfb2979a7bbff3f69f58f58ae324608821e27" in upsampler
    assert "Modifications by PDFScoreBar contributors" in upsampler
    # No StyleGAN2 / NVIDIA-NC derived file may be vendored.
    names = {path.name for path in VENDORED.iterdir()}
    assert not any("stylegan" in name or "upfirdn" in name or "fused" in name for name in names)


def test_dockerfile_drops_realesrgan_install_and_transformer_init() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "xinntao/Real-ESRGAN.git" not in dockerfile
    assert "basicsr' / 'data' / 'degradations.py" not in dockerfile
    assert "homr.main --init" not in dockerfile.replace("`homr.main --init`", "")
    assert "RUN /opt/venv_pipeline/bin/python docker/init_homr_segnet.py" in dockerfile
    for module in EXCLUDED:
        assert f"'{module}'" in dockerfile
    # Issue #533: no Real-ESRGAN release weight is downloaded; first-party SR is used.
    assert "RealESRGAN_x4plus.pth" not in dockerfile


def test_runtime_contract_rejects_excluded_sr_distributions() -> None:
    module_path = ROOT / "docker" / "runtime_contract.py"
    spec = importlib.util.spec_from_file_location("issue533_runtime_contract", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert set(module.EXCLUDED_RUNTIME_MODULES) == set(EXCLUDED)
    assert "realesrgan" not in module.RUNTIME_MODULES
    assert "basicsr" not in module.RUNTIME_MODULES
    assert Path("docker/init_homr_segnet.py") in module.RUNTIME_CONTRACT_FILES


def test_vendored_rrdbnet_matches_released_state_dict_layout() -> None:
    torch = pytest.importorskip("torch")
    from src.third_party.realesrgan_sr import RRDBNet

    x4 = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    keys = list(x4.state_dict())
    assert keys[:2] == ["conv_first.weight", "conv_first.bias"]
    assert "body.22.rdb3.conv5.weight" in keys
    assert keys[-2:] == ["conv_last.weight", "conv_last.bias"]
    assert len(keys) == 2 * (2 + 23 * 3 * 5 + 4)
    x2 = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=8, num_block=1, num_grow_ch=4, scale=2)
    assert x2.conv_first.in_channels == 12
    with torch.no_grad():
        assert tuple(x2(torch.zeros(1, 3, 8, 6)).shape) == (1, 3, 16, 12)


def test_vendored_upsampler_rejects_remote_weights(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from src.third_party.realesrgan_sr import RealESRGANer, RRDBNet

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=8, num_block=1, num_grow_ch=4, scale=4)
    with pytest.raises(ValueError, match="local, verified weight"):
        RealESRGANer(scale=4, model_path="https://example.invalid/w.pth", model=model)


def test_vendored_upsampler_enhance_tiles_on_cpu(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    from src.third_party.realesrgan_sr import RealESRGANer, RRDBNet

    torch.manual_seed(0)
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=8, num_block=1, num_grow_ch=4, scale=4)
    weights = tmp_path / "w.pth"
    torch.save({"params_ema": model.state_dict()}, weights)
    image = np.random.default_rng(0).integers(0, 256, (21, 17, 3), dtype=np.uint8)
    outputs = []
    for tile in (0, 8):
        upsampler = RealESRGANer(
            scale=4,
            model_path=str(weights),
            model=RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=8, num_block=1, num_grow_ch=4, scale=4
            ),
            tile=tile,
            tile_pad=4,
            pre_pad=0,
            half=False,
            device=torch.device("cpu"),
        )
        output, mode = upsampler.enhance(image, outscale=4)
        assert mode == "RGB" and output.shape == (84, 68, 3) and output.dtype == np.uint8
        outputs.append(output)
    gray, gray_mode = upsampler.enhance(image[:, :, 0], outscale=4)
    assert gray_mode == "L" and gray.shape == (84, 68)


def _predictor_module():
    pytest.importorskip("homr")
    from src.homr_runtime import predictor

    return predictor


def test_homr_segnet_only_run_never_calls_transformer(monkeypatch, tmp_path: Path) -> None:
    predictor = _predictor_module()
    cleaned = []
    debug = SimpleNamespace(
        original_image=np.zeros((40, 30), np.uint8),
        clean_debug_files_from_previous_runs=lambda: cleaned.append(True),
    )
    box = SimpleNamespace(to_bounding_box=lambda: SimpleNamespace(box=(1, 2, 3, 20)), debug_id=7)
    notehead = np.ones((40, 30), np.uint8)
    staff = np.zeros((40, 30), np.uint8)
    monkeypatch.setattr(
        predictor,
        "detect_staffs_with_barlines",
        lambda *args: ([], None, debug, None, [box], notehead, staff),
    )
    import homr.main as homr_main

    def forbidden(*args, **kwargs):
        raise AssertionError("transformer transcription must not run")

    monkeypatch.setattr(homr_main, "parse_staffs", forbidden)
    monkeypatch.setattr(predictor, "generate_xml", forbidden)
    image = tmp_path / "page.png"
    result = predictor.run_homr_on_image(
        image, SimpleNamespace(), None, 0.0, {}, False, transcribe_staffs=False
    )
    predictions, xml_path, seg_shape, _runtime, notehead_out, staff_out = result
    assert xml_path is None and seg_shape == (40, 30) and cleaned == [True]
    assert [p.pred_bbox for p in predictions] == [(1, 2, 3, 20)]
    assert predictions[0].system_index == 7
    assert notehead_out is notehead and staff_out is staff


def test_homr_predictor_default_requires_segnet_only(monkeypatch) -> None:
    predictor = _predictor_module()
    calls = []
    monkeypatch.setattr(
        predictor,
        "download_weights",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transformer download")),
    )
    monkeypatch.setattr(predictor, "ensure_segnet_weights", lambda gpu: calls.append(gpu))
    instance = predictor.HomrPredictor(SimpleNamespace(), {}, enable_cache=False)
    assert instance.transcribe_staffs is False
    assert calls == [False]


def test_production_homr_workers_disable_transcription() -> None:
    for name in ("maintained_homr_worker.py", "current_homr_worker.py"):
        source = (ROOT / "src" / "pipeline" / "detection" / name).read_text(encoding="utf-8")
        assert "transcribe_staffs=False" in source, name
    maintained = (ROOT / "src/pipeline/detection/maintained_homr_worker.py").read_text(
        encoding="utf-8"
    )
    assert "transformer_encoder_fp16" not in maintained


def test_rebuild_pins_transitive_versions_of_the_audited_image() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pin in ("filelock==4.2.9", "cuda-pathfinder==1.8.6", "pypdfium2==5.15.1"):
        assert f'"{pin}"' in pyproject


# --- #553: rights/notice/source gate for the Windows portable folder ---------------------
# tools/licensing/portable_compliance.py maps a built folder's build_manifest.json onto the
# reviewed dispositions of docs/licensing/windows_portable_components.json.

import hashlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "portable_compliance", ROOT / "tools" / "licensing" / "portable_compliance.py"
)
pc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = pc
_spec.loader.exec_module(pc)

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
    # Not shipped (#553): removed at build time or installed by the recipient at setup.
    for cid in ("nvidia-unlisted", "triton-recipient", "opencv-ffmpeg"):
        assert components[cid]["disposition"] == "exclude", cid
    assert policy["distributions"]["triton-windows"]["component"] == "triton-recipient"
    acquired = {a["name"]: a for a in policy["recipient_acquired"]}
    assert "ptxas.exe" in acquired["triton-windows"]["license"]
    assert components["barline-cnn-weights"]["disposition"] == "cleared_with_notice"
    assert components["mmr-weights"]["disposition"] == "cleared_with_notice"
    assert "ImageNet-use caution" in components["barline-cnn-weights"]["obligations"][0]
    assert "NOT included" in components["mmr-weights"]["review_note"]
    # First-party licensing is still a single distinct gate; model provenance is not another blocker.
    assert components["pdfscorebar-first-party"]["disposition"] == "permission_needed"
    unlisted = [r["pattern"] for r in policy["file_rules"] if r["component"] == "nvidia-unlisted"]
    assert any(p.endswith("nvperf_host.dll") for p in unlisted)
    assert any(p.endswith("cusolverMg64_*.dll") for p in unlisted)


def test_repository_policy_routes_unlisted_nvidia_before_catch_all():
    policy = pc.load_policy(pc.DEFAULT_POLICY)
    rules = policy["file_rules"]
    hit = pc.match_rule(SP + "triton/backends/nvidia/bin/ptxas.exe", rules)
    assert hit["component"] == "triton-recipient"
    hit = pc.match_rule(SP + "torch/lib/nvperf_host.dll", rules)
    assert hit["component"] == "nvidia-unlisted"
    hit = pc.match_rule(SP + "cv2/opencv_videoio_ffmpeg4110_64.dll", rules)
    assert hit["component"] == "opencv-ffmpeg"
    hit = pc.match_rule("python/Lib/site-packages/pdfscorebar_addons.pth", rules)
    assert hit["component"] == "pdfscorebar-first-party"
    hit = pc.match_rule(SP + "torch/lib/cublas64_12.dll", rules)
    assert hit["component"] == "nvidia-cuda-redistributable"
    hit = pc.match_rule(SP + "torch/lib/cudnn_ops64_9.dll", rules)
    assert hit["component"] == "nvidia-cudnn"
    hit = pc.match_rule(SP + "torch/lib/libiomp5md.dll", rules)
    assert hit["component"] == "intel-openmp"


def test_cleared_folder_passes_and_bundle_is_adjacent(tmp_path):
    policy = _policy(
        recipient_acquired=[{"name": "addon", "version": "2.0", "source": "PyPI", "license": "MIT"}]
    )
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
    notices = (out / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Obtained by the recipient" in notices and "| addon 2.0 | PyPI | MIT |" in notices
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


def test_version_update_needs_a_license_review_and_model_bytes_stay_pinned(tmp_path):
    policy = _policy()
    root = _folder(tmp_path, BASE_FILES, {"demo-pkg": "1.1"})
    manifest, _ = pc.load_manifest(_manifest(root))
    ev = pc.evaluate(manifest, pc.load_policy(_write_policy(tmp_path, policy)))
    # A different package version is not an integrity error, only an unreviewed license.
    assert ev.errors == []
    assert ev.blocked == {"permissive": ["license not reviewed for demo-pkg==1.1 (reviewed 1.0)"]}
    policy["file_rules"][2]["sha256"] = "0" * 64
    ev = pc.evaluate(manifest, pc.load_policy(_write_policy(tmp_path, policy)))
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
