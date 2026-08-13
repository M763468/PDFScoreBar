from pathlib import Path

import pytest

import src.pipeline.detection as detection
import src.pipeline.detection.restored_orchestrator as restored


def _dense_config(*, profile: str | None = "stage_e_verified") -> dict:
    det = {"detector_route": "dense_full_pipeline"}
    if profile is not None:
        det["homr_profile"] = profile
    return {"detection": det}


def test_dense_route_without_profile_reaches_restored_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="homr_profile"):
        detection.run_detection_step(
            config=_dense_config(profile=None),
            images=[],
            page_ids=[],
            run_id="test",
            run_dir=tmp_path,
            dry_run=True,
        )


def test_verified_route_rejects_duplicate_image_stems_before_outputs_collide(
    tmp_path: Path,
) -> None:
    first = tmp_path / "ScoreA" / "page_001.png"
    second = tmp_path / "ScoreB" / "page_001.png"

    with pytest.raises(ValueError, match="unique image stems"):
        detection.run_detection_step(
            config=_dense_config(),
            images=[first, second],
            page_ids=["ScoreA/page_001", "ScoreB/page_001"],
            run_id="test",
            run_dir=tmp_path / "run",
            dry_run=True,
        )


def test_exported_orchestrator_dispatches_dense_route(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    class FakeVerifiedDetectorOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        restored,
        "DetectorOrchestrator",
        FakeVerifiedDetectorOrchestrator,
    )

    image = tmp_path / "Score" / "page_001.png"
    instance = detection.DetectorOrchestrator(
        _dense_config(),
        [image],
        "test",
        tmp_path / "run",
        dry_run=True,
    )

    assert isinstance(instance, FakeVerifiedDetectorOrchestrator)
    assert captured["config"] == _dense_config()
    assert captured["images"] == [image]
    assert captured["run_id"] == "test"
    assert captured["run_dir"] == tmp_path / "run"
    assert captured["dry_run"] is True
    assert captured["in_memory_images"] is None
