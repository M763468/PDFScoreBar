from pathlib import Path

import src.pipeline.detection.profile_hybrid as profile_hybrid


def _detector(tmp_path: Path, images: list[Path]) -> profile_hybrid.VerifiedProfileHybridDetector:
    return profile_hybrid.VerifiedProfileHybridDetector(
        det_cfg={
            "enable_sr": True,
            "sr_scale": 4,
            "homr_profile": "stage_e_verified",
            "detector_route": "dense_full_pipeline",
            "probe_use_original_images": True,
            "cnn_threshold": 0.1,
            "cnn_apply_nms": False,
        },
        images=images,
        run_id="test",
        project_root=tmp_path,
        dry_run=False,
        skip_existing=False,
        profile_name="stage_e_verified",
    )


def test_verified_sources_complete_all_heavy_phases_before_next_page(
    tmp_path: Path, monkeypatch
) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    images = [score / "page_001.png", score / "page_002.png"]
    for image in images:
        image.write_bytes(b"image")

    detector = _detector(tmp_path, images)
    calls: list[tuple[str, str]] = []

    baseline_output = tmp_path / "baseline"
    support_output = tmp_path / "support"
    verified_sr_output = tmp_path / "sr"

    def expected_sr(image: Path) -> Path:
        return (
            support_output
            / image.parent.name
            / image.stem
            / "artifacts"
            / "sr"
            / "batch"
            / image.stem
            / image.name
        ).resolve()

    def fake_profile(
        profile_name: str,
        *,
        images: list[Path],
        output_root: Path,
        precomputed_sr=None,
    ):
        assert profile_name == "stage_e_verified"
        assert len(images) == 1
        image = images[0]
        phase = "verified_sr" if precomputed_sr is not None else "baseline"
        if precomputed_sr is not None:
            assert precomputed_sr == {image: expected_sr(image)}
        calls.append((phase, image.stem))
        output_root.mkdir(parents=True, exist_ok=True)
        return {"commands": [[phase, image.stem]]}

    def fake_support(*, image: Path, output_root: Path):
        assert output_root == support_output
        calls.append(("support", image.stem))
        artifacts = output_root / image.parent.name / image.stem / "artifacts"
        sr = artifacts / "sr" / "batch" / image.stem / image.name
        omr = artifacts / "omr_sr" / image.stem / "predictions.json"
        sr.parent.mkdir(parents=True)
        omr.parent.mkdir(parents=True)
        sr.write_bytes(b"sr")
        omr.write_text("[]\n", encoding="utf-8")
        return (
            {
                "status": "completed",
                "sr_image": str(sr),
                "current_omr": str(omr),
                "historical_detector_artifact_runtime_input": False,
            },
            ["support", image.stem],
        )

    monkeypatch.setattr(profile_hybrid, "run_homr_profile", fake_profile)
    monkeypatch.setattr(detector, "_support_worker", fake_support)

    sr_images, omr_predictions, commands = detector._generate_page_sources(
        baseline_output=baseline_output,
        support_output=support_output,
        verified_sr_output=verified_sr_output,
    )

    assert calls == [
        ("baseline", "page_001"),
        ("support", "page_001"),
        ("verified_sr", "page_001"),
        ("baseline", "page_002"),
        ("support", "page_002"),
        ("verified_sr", "page_002"),
    ]
    assert sr_images == {image: expected_sr(image) for image in images}
    assert list(omr_predictions) == images
    assert commands == [
        ["baseline", "page_001"],
        ["support", "page_001"],
        ["verified_sr", "page_001"],
        ["baseline", "page_002"],
        ["support", "page_002"],
        ["verified_sr", "page_002"],
    ]
