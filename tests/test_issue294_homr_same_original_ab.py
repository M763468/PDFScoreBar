import json
from pathlib import Path

from tools.issue294.compare_same_original_ab import (
    EXPECTED_HOMR_COMMIT,
    box_comparison,
    maintained_runtime_contract,
)
from tools.issue294.replay_hybrid_with_fixed_support import compare_page

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_detection(path: Path, boxes: list[tuple[int, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "predictions": [
                    {
                        "pred_bbox": list(box),
                        "orig_bbox": list(box),
                        "system_index": 0,
                        "staff_index": 0,
                    }
                    for box in boxes
                ]
            }
        ),
        encoding="utf-8",
    )


def _model_provenance() -> dict[str, dict[str, object]]:
    return {
        "segnet_fp16": {"exists": True, "sha256": "a" * 64},
        "transformer_encoder_fp16": {"exists": True, "sha256": "b" * 64},
        "transformer_decoder_fp16": {"exists": True, "sha256": "c" * 64},
    }


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


def test_issue294_runtime_contract_requires_all_models_cuda_and_coordinates() -> None:
    worker = {
        "runtime": {"homr_installed_commit": EXPECTED_HOMR_COMMIT},
        "models": _model_provenance(),
        "onnx_sessions": [
            {
                "model": "/tmp/segnet_308_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
            {
                "model": "/tmp/encoder_model_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
            {
                "model": "/tmp/decoder_model_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
        ],
        "coordinate_checks": {"masks_match_original_shape": True},
        "artifacts": {"connector_complete": True},
    }

    result = maintained_runtime_contract(worker)

    assert result["commit_verified"] is True
    assert result["all_required_fp16_roles_cuda_first"] is True
    assert result["model_hashes_captured"] is True
    assert result["coordinate_contract"] is True
    assert result["connector_complete"] is True
    assert result["hard_contract_pass"] is True


def test_issue294_runtime_contract_rejects_fp16_cpu_fallback() -> None:
    worker = {
        "runtime": {"homr_installed_commit": EXPECTED_HOMR_COMMIT},
        "models": _model_provenance(),
        "onnx_sessions": [
            {
                "model": "/tmp/segnet_308_fp16.onnx",
                "active_providers": ["CPUExecutionProvider"],
            },
            {
                "model": "/tmp/encoder_model_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider"],
            },
            {
                "model": "/tmp/decoder_model_fp16.onnx",
                "active_providers": ["CUDAExecutionProvider"],
            },
        ],
        "coordinate_checks": {"masks_match_original_shape": True},
        "artifacts": {"connector_complete": True},
    }

    result = maintained_runtime_contract(worker)

    assert result["fp16_cuda_first_provider_by_role"]["segnet"] is False
    assert result["all_required_fp16_roles_cuda_first"] is False
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


def test_issue294_fixed_support_replay_changes_only_baseline(tmp_path: Path) -> None:
    score = "SyntheticScore"
    stem = "page_013"
    image = tmp_path / score / f"{stem}.png"

    a_detection = tmp_path / "ab" / "A.json"
    b_detection = tmp_path / "ab" / "B.json"
    _write_detection(a_detection, [(10, 10, 14, 100), (50, 20, 54, 110)])
    _write_detection(b_detection, [(11, 10, 15, 100), (80, 20, 84, 110)])

    support_root = tmp_path / "support"
    page_root = support_root / score / stem
    x4_detection = (
        page_root
        / "artifacts/current_homr/batch"
        / stem
        / f"{stem}_detections.json"
    )
    omr_detection = page_root / "artifacts/omr_sr" / stem / "predictions.json"
    _write_detection(x4_detection, [(10, 10, 14, 100)])
    omr_detection.parent.mkdir(parents=True, exist_ok=True)
    omr_detection.write_text("[]\n", encoding="utf-8")
    page_root.mkdir(parents=True, exist_ok=True)
    (page_root / "result.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "connector_complete": True,
                "historical_detector_artifact_runtime_input": False,
            }
        ),
        encoding="utf-8",
    )

    page = {
        "image": str(image),
        "A_pinned": {"artifacts": {"detections": str(a_detection)}},
        "B_maintained": {"worker": {"artifacts": {"detections": str(b_detection)}}},
    }
    output_root = tmp_path / "replay"

    result = compare_page(page, support_root, output_root)

    assert result["support"]["shared_by_A_and_B"] is True
    assert result["hybrid_counts"] == {"A": 1, "B": 1}
    assert result["hybrid_delta"]["exact_multiset_equal"] is False
    assert result["hybrid_delta"]["matched_center_anchor"] == 1
    assert result["hybrid_delta"]["coordinate_review_required"] is True


def test_issue294_host_runner_can_attach_fixed_support_replay() -> None:
    source = (PROJECT_ROOT / "tools/issue294/run_same_original_ab_host.py").read_text(
        encoding="utf-8"
    )

    assert 'CONTAINER = "pdfscore_issue293_profile"' in source
    assert "--support-root" in source
    assert "replay_hybrid_with_fixed_support.py" in source
    assert "fixed_support_replay" in source
