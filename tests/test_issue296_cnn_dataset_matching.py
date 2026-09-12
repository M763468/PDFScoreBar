import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.pipeline.detection.restored_orchestrator import DetectorOrchestrator
from tools.cnn_classifier.build_cnn_dataset import _is_canonical_candidate_match


def _run_builder(script: Path, args: list[str], *, cwd: Path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _verified_orchestrator(tmp_path: Path, det_cfg: dict):
    obj = object.__new__(DetectorOrchestrator)
    obj.det_cfg = det_cfg
    obj._dense_route = None
    obj.dry_run = True
    obj.run_dir = tmp_path
    obj.probe_output_dir = None
    obj.images = []
    obj.in_memory_images = None
    return obj


def test_candidate_with_no_horizontal_iou_can_still_be_canonical_positive():
    gt_box = [100, 100, 104, 200]
    candidate = [108, 100, 112, 200]

    assert candidate[0] > gt_box[2]
    assert _is_canonical_candidate_match(candidate, gt_box, unit_size=24.0) is True


def test_candidate_outside_center_anchor_xdist_is_negative():
    gt_box = [100, 100, 104, 200]
    candidate = [115, 100, 119, 200]

    assert _is_canonical_candidate_match(candidate, gt_box, unit_size=24.0) is False


def test_candidate_requires_half_vertical_overlap():
    gt_box = [100, 100, 104, 200]
    candidate = [100, 160, 104, 240]

    assert _is_canonical_candidate_match(candidate, gt_box, unit_size=24.0) is False


def test_dataset_builder_help_works_without_pythonpath(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "cnn_classifier" / "build_cnn_dataset.py"

    result = _run_builder(script, ["--help"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Build CNN classifier dataset" in result.stdout


def test_dataset_builder_rejects_obsolete_iou_threshold_option(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "cnn_classifier" / "build_cnn_dataset.py"

    result = _run_builder(script, ["--iou-threshold", "0.5", "--only-split"], cwd=tmp_path)

    assert result.returncode != 0
    assert "unrecognized arguments: --iou-threshold 0.5" in result.stderr


def test_verified_route_requires_explicit_cnn_threshold(tmp_path):
    orchestrator = _verified_orchestrator(
        tmp_path,
        {
            "cnn_model_path": "model.pth",
            "cnn_apply_nms": False,
        },
    )

    with pytest.raises(ValueError, match="explicit detection.cnn_threshold"):
        orchestrator._run_cnn_scoring()


def test_verified_route_requires_explicit_cnn_apply_nms(tmp_path):
    orchestrator = _verified_orchestrator(
        tmp_path,
        {
            "cnn_model_path": "model.pth",
            "cnn_threshold": 0.4965248107910156,
        },
    )

    with pytest.raises(ValueError, match="explicit detection.cnn_apply_nms=false"):
        orchestrator._run_cnn_scoring()


def test_verified_route_rejects_cnn_nms_enabled(tmp_path):
    orchestrator = _verified_orchestrator(
        tmp_path,
        {
            "cnn_model_path": "model.pth",
            "cnn_threshold": 0.4965248107910156,
            "cnn_apply_nms": True,
        },
    )

    with pytest.raises(ValueError, match="requires cnn_apply_nms=false"):
        orchestrator._run_cnn_scoring()


def test_verified_route_accepts_explicit_d27_scoring_contract_in_dry_run(tmp_path):
    orchestrator = _verified_orchestrator(
        tmp_path,
        {
            "cnn_model_path": "model.pth",
            "cnn_threshold": 0.4965248107910156,
            "cnn_apply_nms": False,
        },
    )

    result = orchestrator._run_cnn_scoring()

    assert result["commands"][0][0] == "inprocess:cnn_scoring"
    assert result["commands"][0][-1] == "False"
