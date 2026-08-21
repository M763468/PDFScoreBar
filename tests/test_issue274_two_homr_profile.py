from pathlib import Path
from typing import Any

import pytest

import src.pipeline.detection.profile_hybrid as profile_hybrid
from src.pipeline.detection.current_support_worker import _require_current_homr_bundle
from src.pipeline.detection.profile_hybrid import VerifiedProfileHybridDetector


def _detector(
    *,
    tmp_path: Path,
    image: Path,
    dry_run: bool,
) -> VerifiedProfileHybridDetector:
    return VerifiedProfileHybridDetector(
        det_cfg={
            "enable_sr": True,
            "sr_scale": 4,
            "hybrid_output_root": str(tmp_path / "hybrid"),
        },
        images=[image],
        run_id="issue274_two_homr",
        project_root=tmp_path,
        dry_run=dry_run,
        skip_existing=False,
        profile_name="stage_e_verified_homr",
    )


def test_in_process_source_generation_reuses_current_x4_detection(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    image = tmp_path / "score" / "page.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"page")

    sr_image = tmp_path / "support" / "page_x4.png"
    current_detection = tmp_path / "support" / "page_detections.json"
    omr = tmp_path / "support" / "predictions.json"
    for path in (sr_image, current_detection, omr):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

    homr_calls: list[Path] = []

    def fake_run_homr_profile(
        profile_name: str,
        *,
        images: list[Path],
        output_root: Path,
    ) -> dict[str, Any]:
        assert profile_name == "stage_e_verified_homr"
        assert output_root == tmp_path / "baseline"
        homr_calls.extend(images)
        return {"commands": [["profile:homr", profile_name, "baseline", str(images[0])]]}

    detector = _detector(tmp_path=tmp_path, image=image, dry_run=False)

    def fake_support_worker(
        *,
        image: Path,
        output_root: Path,
    ) -> tuple[dict[str, Any], list[str]]:
        assert image.is_file()
        assert output_root == tmp_path / "support-output"
        return (
            {
                "sr_image": str(sr_image),
                "current_sr_detection": str(current_detection),
                "current_omr": str(omr),
            },
            ["current-support", str(image)],
        )

    monkeypatch.setattr(profile_hybrid, "run_homr_profile", fake_run_homr_profile)
    monkeypatch.setattr(detector, "_support_worker", fake_support_worker)

    result = detector._generate_one_page_sources_in_process(
        image=image,
        baseline_output=tmp_path / "baseline",
        support_output=tmp_path / "support-output",
    )

    assert homr_calls == [image]
    assert Path(result["current_sr_detection"]) == current_detection.resolve()
    assert result["homr_neural_inference_count"] == 2
    assert result["x4_homr_neural_inference_count"] == 1
    assert result["x4_detector_support_owner"] == "current_x4_support"
    assert result["commands"] == [
        ["profile:homr", "stage_e_verified_homr", "baseline", str(image)],
        ["current-support", str(image)],
    ]


def test_dry_run_declares_one_x4_homr_owner(tmp_path: Path) -> None:
    image = tmp_path / "score" / "page.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"page")

    detector = _detector(tmp_path=tmp_path, image=image, dry_run=True)
    result = detector.run()

    profile_commands = [
        command for command in result["commands"] if command and command[0] == "profile:homr"
    ]
    assert len(profile_commands) == 1
    assert profile_commands[0][2] == "baseline"
    assert result["homr_neural_inference_count_per_page"] == 2
    assert result["x4_homr_neural_inference_count_per_page"] == 1
    assert result["x4_detector_support_owner"] == "current_x4_support"
    assert "verified_homr_on_fresh_x4_per_page" not in result["source_generation_phases"]
    assert "current_x4_detection_reused_for_consensus" in result["source_generation_phases"]


def test_current_x4_support_rejects_incomplete_connector_bundle() -> None:
    with pytest.raises(RuntimeError, match="complete connector semantic pair"):
        _require_current_homr_bundle(
            {
                "connector_complete": False,
                "current_sr_detection": "unused.json",
                "staff_mask": "unused.png",
            }
        )


def test_current_x4_support_requires_all_canonical_artifacts(tmp_path: Path) -> None:
    paths = {
        "current_sr_detection": tmp_path / "detections.json",
        "staff_mask": tmp_path / "staff.png",
        "connector_symbols": tmp_path / "symbols.png",
        "connector_brace_dot": tmp_path / "brace_dot.png",
    }
    for path in paths.values():
        path.write_bytes(b"artifact")

    resolved = _require_current_homr_bundle(
        {
            "connector_complete": True,
            **{name: str(path) for name, path in paths.items()},
        }
    )

    assert resolved == {name: path.resolve() for name, path in paths.items()}
