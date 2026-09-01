from pathlib import Path

from tools.issue294.compare_same_original_ab import (
    EXPECTED_HOMR_COMMIT,
    box_comparison,
    maintained_runtime_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issue294_box_comparison_reports_exact_and_consensus_parity() -> None:
    left = [(10, 10, 14, 100), (50, 20, 54, 110)]
    right = [(10, 10, 14, 100), (51, 20, 55, 110)]

    result = box_comparison(left, right)

    assert result["ordered_equal"] is False
    assert result["multiset_equal"] is False
    assert result["exact_multiset_intersection_count"] == 1
    assert result["left_only_exact_count"] == 1
    assert result["right_only_exact_count"] == 1
    assert result["left_supported_by_right_iou_gt_0_5"] == 2
    assert result["right_supported_by_left_iou_gt_0_5"] == 2
    assert result["left_support_fraction"] == 1.0
    assert result["right_support_fraction"] == 1.0


def test_issue294_runtime_contract_requires_pinned_commit_cuda_and_coordinates() -> None:
    worker = {
        "runtime": {"homr_installed_commit": EXPECTED_HOMR_COMMIT},
        "onnx_sessions": [
            {
                "model": "/tmp/segnet_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
            {
                "model": "/tmp/encoder_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
        ],
        "coordinate_checks": {"masks_match_original_shape": True},
        "artifacts": {"connector_complete": True},
    }

    result = maintained_runtime_contract(worker)

    assert result["commit_verified"] is True
    assert result["fp16_cuda_first_provider"] is True
    assert result["coordinate_contract"] is True
    assert result["connector_complete"] is True
    assert result["hard_contract_pass"] is True


def test_issue294_runtime_contract_rejects_fp16_cpu_fallback() -> None:
    worker = {
        "runtime": {"homr_installed_commit": EXPECTED_HOMR_COMMIT},
        "onnx_sessions": [
            {
                "model": "/tmp/segnet_fp16.onnx",
                "active_providers": ["CPUExecutionProvider"],
            }
        ],
        "coordinate_checks": {"masks_match_original_shape": True},
        "artifacts": {"connector_complete": True},
    }

    result = maintained_runtime_contract(worker)

    assert result["fp16_cuda_first_provider"] is False
    assert result["hard_contract_pass"] is False


def test_issue294_candidate_worker_is_original_image_only() -> None:
    source = (
        PROJECT_ROOT / "tools/issue294/run_maintained_homr_original.py"
    ).read_text(encoding="utf-8")

    assert "sr_scale=1" in source
    assert "sr_scale=4" not in source
    assert "coord / sr_scale" not in source
    assert "coordinate_space\": \"original_page" in source


def test_issue294_runner_keeps_pinned_profile_as_variant_a() -> None:
    source = (PROJECT_ROOT / "tools/issue294/run_same_original_ab.py").read_text(
        encoding="utf-8"
    )

    assert 'PROFILE_NAME = "stage_e_verified"' in source
    assert "build_profile_command" in source
    assert "run_maintained_homr_original.py" in source
    assert '"input_contract": "same_original_page"' in source
