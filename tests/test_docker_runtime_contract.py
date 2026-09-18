from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

from src.common.realesrgan_assets import resolve_realesrgan_weight
from src.pipeline.detection.omr_dln_model import resolve_omr_dln_model_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_contract_module():
    module_path = PROJECT_ROOT / "docker" / "runtime_contract.py"
    spec = importlib.util.spec_from_file_location("pdfscore_runtime_contract", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_realesrgan_weight_override_is_independent_of_workspace(tmp_path: Path) -> None:
    asset_root = tmp_path / "image-assets"
    expected = asset_root / "RealESRGAN_x2plus.pth"

    resolved = resolve_realesrgan_weight(
        "RealESRGAN_x2plus",
        project_root=tmp_path / "workspace",
        environment={"PDFSCORE_REALESRGAN_WEIGHTS_DIR": str(asset_root)},
    )

    assert resolved == expected


def test_omr_dln_model_accepts_explicit_external_asset(tmp_path: Path) -> None:
    expected = tmp_path / "YOLOv8m_Measures.pt"

    resolved = resolve_omr_dln_model_path(
        repository_root=tmp_path / "workspace",
        environment={"OMR_DLN_MODEL_PATH": str(expected)},
    )

    assert resolved == expected


def test_source_fingerprint_detects_runtime_source_drift_but_ignores_config(tmp_path: Path) -> None:
    runtime_contract = _load_runtime_contract_module()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "smoke.yaml").write_text("value: 1\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")

    initial = runtime_contract.source_fingerprint(tmp_path)
    (tmp_path / "configs" / "smoke.yaml").write_text("value: 2\n", encoding="utf-8")
    assert runtime_contract.source_fingerprint(tmp_path) == initial

    (tmp_path / "src" / "worker.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert runtime_contract.source_fingerprint(tmp_path) != initial


def _write_fake_docker(bin_dir: Path) -> Path:
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >>"$DOCKER_CALL_LOG"\n'
        'if [[ "${1:-} ${2:-}" == "image ls" ]]; then echo "fake-image-id"; fi\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return docker


def _run_make_with_fake_docker(target: str, tmp_path: Path) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_docker(bin_dir)
    call_log = tmp_path / "docker_calls.log"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["DOCKER_CALL_LOG"] = str(call_log)

    result = subprocess.run(
        ["make", target],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return call_log.read_text(encoding="utf-8").splitlines()


def test_docker_clean_removes_only_the_canonical_container(tmp_path: Path) -> None:
    calls = _run_make_with_fake_docker("docker-clean", tmp_path)

    assert calls == ["rm -f pdfscore_pipeline_gpu"]


def test_docker_clean_full_removes_container_then_image(tmp_path: Path) -> None:
    calls = _run_make_with_fake_docker("docker-clean-full", tmp_path)

    assert calls == [
        "rm -f pdfscore_pipeline_gpu",
        "image ls --quiet pdfscore_pipeline_gpu",
        "rmi pdfscore_pipeline_gpu",
    ]
