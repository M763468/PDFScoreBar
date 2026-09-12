from pathlib import Path

import pytest

from src.pipeline.detection.homr_profile import (
    build_profile_command,
    build_profile_environment,
    load_homr_profile,
)


def test_stage_e_verified_profile_is_pinned_and_artifact_free() -> None:
    profile = load_homr_profile("stage_e_verified")

    assert profile["historical_detector_artifact_runtime_input"] is False
    assert profile["homr"]["commit"] == "864e2882f7a41afcf8f16654728a473ae56826d6"
    assert profile["pdfscore_evaluator"]["commit"] == "bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7"
    assert profile["packages"] == {
        "numpy": "2.2.6",
        "opencv-python-headless": "4.12.0.88",
        "onnxruntime-gpu": "1.22.0",
    }
    assert profile["verified_stage_e_full68"] == {
        "gt": 3567,
        "pred": 3599,
        "tp": 3565,
        "fp": 3,
        "fn": 2,
        "fn_det": 0,
        "fn_cnn": 2,
        "soft_duplicate_or_repeat_like": 31,
        "cnn_threshold": 0.1,
        "cnn_apply_nms": False,
        "sr_scale": 4,
        "canonical_gt_rebase_issue": 291,
        "evaluated_artifact": "pipeline2_no_peak_filtered_cnn.json",
    }


def test_profile_environment_prioritizes_pinned_sources(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/existing")
    profile = load_homr_profile("stage_e_verified")

    env = build_profile_environment(profile)
    entries = env["PYTHONPATH"].split(":")

    assert entries[:4] == [
        "/opt/homr_stage_e_profile",
        "/opt/pdfscore_stage_e_profile",
        "/opt/pdfscore_stage_e_profile/src",
        str(Path(__file__).resolve().parents[1]),
    ]
    assert entries[-1] == "/existing"


def test_profile_command_uses_isolated_python_and_precomputed_sr() -> None:
    profile = load_homr_profile("stage_e_verified")
    image = Path("/workspace/data/evaluation2/images/Score/page_001.png")
    sr = Path("/workspace/logs/sr_source/page_001.png")

    command = build_profile_command(
        profile,
        images=[image],
        output_root=Path("/workspace/logs/profile_sr"),
        precomputed_sr=sr,
    )

    assert command[0] == "/opt/venv_stage_e_homr/bin/python"
    assert command[1] == "/workspace/src/pipeline/detection/homr_profile_compat.py"
    assert "--pre-computed-sr" in command
    assert command[command.index("--pre-computed-sr") + 1] == str(sr)
    assert "--enable-sr" not in command


def test_profile_command_rejects_one_sr_path_for_multiple_images() -> None:
    profile = load_homr_profile("stage_e_verified")

    with pytest.raises(ValueError, match="exactly one image"):
        build_profile_command(
            profile,
            images=[Path("a.png"), Path("b.png")],
            output_root=Path("out"),
            precomputed_sr=Path("sr.png"),
        )
