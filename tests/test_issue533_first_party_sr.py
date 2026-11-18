"""Issue #533: first-party x4 SR model replacing the Real-ESRGAN release weights."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models" / "sr_x4" / "manifest.json"
TOOLS = ROOT / "tools" / "issue533"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_records_clean_provenance_and_matching_bytes() -> None:
    data = _manifest()
    weights = ROOT / data["weights"]
    assert hashlib.sha256(weights.read_bytes()).hexdigest() == data["sha256"]
    assert weights.stat().st_size == data["size_bytes"]
    rights = data["rights"]
    assert rights["initialization"].startswith("random")
    assert rights["teacher"].startswith("none")
    prov = data["provenance"]
    for script, key in (
        ("train_sr.py", "training_script_sha256"),
        ("synth_score.py", "synthetic_data_script_sha256"),
    ):
        assert hashlib.sha256((TOOLS / script).read_bytes()).hexdigest() == prov[key], script


def _calls(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else ""
                names.add(f"{base}.{f.attr}")
            elif isinstance(f, ast.Name):
                names.add(f.id)
    return names


def test_synthetic_data_generator_reads_no_external_images_or_data() -> None:
    calls = _calls(TOOLS / "synth_score.py")
    for forbidden in ("cv2.imread", "open", "np.load", "torch.load", "fitz.open"):
        assert forbidden not in calls, forbidden
    # __main__ preview only writes; no input path is read.


def test_training_script_loads_no_pretrained_weights() -> None:
    source = (TOOLS / "train_sr.py").read_text(encoding="utf-8")
    assert "torch.load" not in source
    assert "load_state_dict" not in source
    assert "RealESRGAN" not in source


def test_synthetic_pairs_are_deterministic() -> None:
    pytest.importorskip("cv2")
    sys.path.insert(0, str(TOOLS))
    import synth_score

    a = synth_score.make_pair(12345, size=256)
    b = synth_score.make_pair(12345, size=256)
    assert all((x == y).all() for x, y in zip(a, b))
    assert a[0].shape == (256, 256) and a[1].shape == (64, 64)


def test_production_sources_no_longer_reference_realesrgan_release_weights() -> None:
    offenders = []
    for base in ("src", "docker"):
        for path in (ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if (
                "RealESRGAN_x4plus" in text
                or "RealESRGAN_x2plus" in text
                or "resolve_realesrgan_weight" in text
            ):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_sr_model_loads_strictly_into_vendored_rrdbnet() -> None:
    torch = pytest.importorskip("torch")
    from src.common.model_artifacts import resolve_first_party_sr
    from src.third_party.realesrgan_sr import RRDBNet

    model = resolve_first_party_sr(project_root=ROOT)
    net = RRDBNet(**model.rrdbnet_kwargs())
    state = torch.load(model.path, map_location="cpu")[model.state_dict_key]
    net.load_state_dict(state, strict=True)
    assert sum(p.numel() for p in net.parameters()) == _manifest()["parameters"]


def test_runtime_contract_resolves_manifest_selected_sr() -> None:
    source = (ROOT / "docker" / "runtime_contract.py").read_text(encoding="utf-8")
    assert "resolve_first_party_sr" in source
