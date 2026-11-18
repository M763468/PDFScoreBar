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
    # Real-ESRGAN release weights remain image-owned and hash-verified.
    assert "RealESRGAN_x4plus.pth" in dockerfile


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
