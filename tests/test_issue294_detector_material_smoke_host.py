from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.issue294 import run_detector_material_smoke_host as smoke


def test_detector_smoke_persists_runs_under_logs() -> None:
    assert smoke.SMOKE_ROOT == smoke.PROJECT_ROOT / "logs/issue294"


def _write_result(
    tmp_path: Path,
    *,
    gpu_requested: bool = True,
    mask_shape: list[int] | None = None,
    optional_modules: list[str] | None = None,
    postrun_optional_modules: list[str] | None = None,
) -> Path:
    artifacts = {}
    for key in ("detections", "staff_mask", "notehead_mask", "clef_mask"):
        path = tmp_path / f"{key}.dat"
        path.write_bytes(b"x")
        artifacts[key] = str(path)

    original_shape = [1920, 2715]
    shape = mask_shape or original_shape
    payload = {
        "status": "completed",
        "homr": {"commit": "457e7c6518a10ba755db2e60883419e56c4d7369"},
        "preflight": {"optional_modules_imported": optional_modules or []},
        "postrun_optional_modules_imported": postrun_optional_modules or [],
        "runtime": {"gpu_requested": gpu_requested},
        "onnx_sessions": [
            {
                "active_providers": [
                    "CUDAExecutionProvider",
                    "CPUExecutionProvider",
                ]
            }
        ],
        "artifacts": artifacts,
        "coordinate_checks": {
            "original_shape_wh": original_shape,
            "staff_mask_shape_wh": shape,
            "notehead_mask_shape_wh": shape,
            "clef_mask_shape_wh": shape,
        },
    }
    result = tmp_path / "result.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    return result


def test_detector_smoke_accepts_completed_cuda_coordinate_contract(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path)

    payload = smoke._load_result(result, label="C_latest", commit=commit)

    assert payload["homr"]["commit"] == commit


def test_detector_smoke_rejects_non_gpu_runtime(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, gpu_requested=False)

    with pytest.raises(RuntimeError, match="did not request GPU runtime"):
        smoke._load_result(result, label="C_latest", commit=commit)


def test_detector_smoke_rejects_coordinate_shape_drift(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, mask_shape=[1919, 2715])

    with pytest.raises(RuntimeError, match="coordinate shape mismatch"):
        smoke._load_result(result, label="C_latest", commit=commit)


def test_detector_smoke_rejects_preflight_optional_module_import(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, optional_modules=["homr.pdf_utils"])

    with pytest.raises(RuntimeError, match="during preflight"):
        smoke._load_result(result, label="C_latest", commit=commit)


def test_detector_smoke_rejects_postrun_optional_module_import(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, postrun_optional_modules=["homr.main"])

    with pytest.raises(RuntimeError, match="after inference"):
        smoke._load_result(result, label="C_latest", commit=commit)


def test_detector_smoke_maps_workspace_artifact_path_to_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(smoke, "PROJECT_ROOT", tmp_path)

    assert smoke._host_path("/workspace/temp/example.json") == tmp_path / "temp/example.json"


def test_detector_smoke_script_direct_execution_bootstraps_repo_root(tmp_path: Path) -> None:
    script = smoke.PROJECT_ROOT / "tools/issue294/run_detector_material_smoke_host.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
    assert "--latest-homr-commit" in completed.stdout
