from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.issue294.run_detector_material_smoke_host import _load_result


def _write_result(tmp_path: Path, *, cuda: bool = True, mask_shape: list[int] | None = None) -> Path:
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
        "runtime": {"cuda": cuda},
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

    payload = _load_result(result, label="C_latest", commit=commit)

    assert payload["homr"]["commit"] == commit


def test_detector_smoke_rejects_non_cuda_runtime(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, cuda=False)

    with pytest.raises(RuntimeError, match="did not use CUDA runtime"):
        _load_result(result, label="C_latest", commit=commit)


def test_detector_smoke_rejects_coordinate_shape_drift(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    result = _write_result(tmp_path, mask_shape=[1919, 2715])

    with pytest.raises(RuntimeError, match="coordinate shape mismatch"):
        _load_result(result, label="C_latest", commit=commit)
