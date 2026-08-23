from pathlib import Path

import pytest

from src.pipeline.detection.current_sr_batch_worker import _items
from src.pipeline.detection.current_support_worker import _require_precomputed_sr
from src.pipeline.detection.profile_hybrid_batch_sr import BatchSRVerifiedProfileHybridDetector


def _detector(tmp_path: Path, images: list[Path]) -> BatchSRVerifiedProfileHybridDetector:
    return BatchSRVerifiedProfileHybridDetector(
        det_cfg={
            "enable_sr": True,
            "sr_scale": 4,
            "hybrid_output_root": str(tmp_path / "hybrid"),
        },
        images=images,
        run_id="issue284_sr_batch",
        project_root=tmp_path,
        dry_run=True,
        skip_existing=False,
        profile_name="stage_e_verified_homr",
    )


def test_precomputed_sr_contract_accepts_current_x4_artifact(tmp_path: Path) -> None:
    image = tmp_path / "score" / "page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"page")
    sr_image = tmp_path / "sr" / "page_001.png"
    sr_image.parent.mkdir(parents=True)
    sr_image.write_bytes(b"sr")

    payload = _require_precomputed_sr(
        {
            "precomputed_sr": {
                "image": str(image),
                "sr_scale": 4,
                "sr_image": str(sr_image),
                "sr_sha256": "abc123",
                "historical_detector_artifact_runtime_input": False,
            }
        },
        image=image.resolve(),
    )

    assert payload is not None
    assert Path(payload["sr_image"]) == sr_image.resolve()
    assert payload["sr_scale"] == 4
    assert payload["sr_sha256"] == "abc123"


def test_precomputed_sr_contract_rejects_wrong_source_page(tmp_path: Path) -> None:
    image = tmp_path / "page_001.png"
    other = tmp_path / "page_002.png"
    sr_image = tmp_path / "sr.png"
    for path in (image, other, sr_image):
        path.write_bytes(b"x")

    with pytest.raises(ValueError, match="image mismatch"):
        _require_precomputed_sr(
            {
                "precomputed_sr": {
                    "image": str(other),
                    "sr_scale": 4,
                    "sr_image": str(sr_image),
                    "sr_sha256": "abc123",
                    "historical_detector_artifact_runtime_input": False,
                }
            },
            image=image.resolve(),
        )


def test_batch_request_rejects_duplicate_images(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"page")

    with pytest.raises(ValueError, match="Duplicate current-SR batch image"):
        _items(
            {
                "items": [
                    {"image": str(image), "output": str(tmp_path / "one.png")},
                    {"image": str(image), "output": str(tmp_path / "two.png")},
                ]
            }
        )


def test_verified_dry_run_declares_one_all_pages_sr_phase(tmp_path: Path) -> None:
    images = [tmp_path / "score" / "page_001.png", tmp_path / "score" / "page_002.png"]
    for image in images:
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"page")

    result = _detector(tmp_path, images).run()

    sr_batch_commands = [
        command
        for command in result["commands"]
        if command and command[0] == "current-sr-batch-worker"
    ]
    assert len(sr_batch_commands) == 1
    assert sr_batch_commands[0][1:] == [str(image) for image in images]
    assert result["source_generation_scope"] == (
        "dedicated_sr_batch_then_top_level_python_per_page"
    )
    assert result["sr_model_lifetime"] == "one_per_detection_call"
    assert result["sr_memory_boundary"] == "batch_process_exits_before_homr_omr"
    assert result["homr_neural_inference_count_per_page"] == 2
    assert result["x4_homr_neural_inference_count_per_page"] == 1
    assert result["source_generation_phases"][0] == "current_x4_sr_batch_all_pages"
