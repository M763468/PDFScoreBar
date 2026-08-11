import json
from pathlib import Path

import src.pipeline.detection.profile_hybrid as profile_hybrid
import src.pipeline.detection.verified_source_page_worker as source_worker


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


def test_one_page_source_worker_runs_all_heavy_phases_in_order(tmp_path: Path, monkeypatch) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    image = score / "page_001.png"
    image.write_bytes(b"image")

    detector = _detector(tmp_path, [image])
    calls: list[tuple[str, str]] = []
    baseline_output = tmp_path / "baseline"
    support_output = tmp_path / "support"
    verified_sr_output = tmp_path / "sr"

    def expected_sr() -> Path:
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
        assert images == [image]
        phase = "verified_sr" if precomputed_sr is not None else "baseline"
        if precomputed_sr is not None:
            assert precomputed_sr == {image: expected_sr()}
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

    payload = detector._generate_one_page_sources_in_process(
        image=image,
        baseline_output=baseline_output,
        support_output=support_output,
        verified_sr_output=verified_sr_output,
    )

    assert calls == [
        ("baseline", "page_001"),
        ("support", "page_001"),
        ("verified_sr", "page_001"),
    ]
    assert Path(payload["sr_image"]) == expected_sr()
    assert Path(payload["current_omr"]).is_file()
    assert payload["commands"] == [
        ["baseline", "page_001"],
        ["support", "page_001"],
        ["verified_sr", "page_001"],
    ]
    assert payload["historical_detector_artifact_runtime_input"] is False


def test_verified_sources_launch_one_top_level_worker_per_page(tmp_path: Path, monkeypatch) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    images = [score / "page_001.png", score / "page_002.png"]
    for image in images:
        image.write_bytes(b"image")

    detector = _detector(tmp_path, images)
    baseline_output = tmp_path / "hybrid" / "baseline"
    support_output = tmp_path / "hybrid" / "support"
    verified_sr_output = tmp_path / "hybrid" / "sr"
    calls: list[Path] = []

    def fake_source_worker(
        *,
        image: Path,
        worker_output: Path,
        baseline_output: Path,
        support_output: Path,
        verified_sr_output: Path,
    ):
        del worker_output, baseline_output, verified_sr_output
        calls.append(image)
        artifacts = support_output / image.parent.name / image.stem / "artifacts"
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
                "commands": [["child", image.stem]],
                "memory_boundary": "top_level_python_per_page",
                "historical_detector_artifact_runtime_input": False,
            },
            ["worker", image.stem],
        )

    monkeypatch.setattr(detector, "_source_page_worker", fake_source_worker)

    sr_images, omr_predictions, commands = detector._generate_page_sources(
        baseline_output=baseline_output,
        support_output=support_output,
        verified_sr_output=verified_sr_output,
    )

    assert calls == images
    assert list(sr_images) == images
    assert list(omr_predictions) == images
    assert commands == [
        ["worker", "page_001"],
        ["child", "page_001"],
        ["worker", "page_002"],
        ["child", "page_002"],
    ]


def test_verified_source_page_worker_records_process_boundary(tmp_path: Path, monkeypatch) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    image = score / "page_001.png"
    image.write_bytes(b"image")
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"

    request.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.verified_source_page_request.v1",
                "detection": _detector(tmp_path, [image]).det_cfg,
                "image": str(image),
                "run_id": "test",
                "project_root": str(tmp_path),
                "profile_name": "stage_e_verified",
                "baseline_output": str(tmp_path / "baseline"),
                "support_output": str(tmp_path / "support"),
                "verified_sr_output": str(tmp_path / "sr"),
            }
        ),
        encoding="utf-8",
    )

    sr = tmp_path / "generated/page_001.png"
    omr = tmp_path / "generated/predictions.json"
    sr.parent.mkdir(parents=True)
    sr.write_bytes(b"sr")
    omr.write_text("[]\n", encoding="utf-8")

    def fake_generate(self, **_kwargs):
        return {
            "sr_image": str(sr),
            "current_omr": str(omr),
            "commands": [["phase"]],
            "historical_detector_artifact_runtime_input": False,
        }

    monkeypatch.setattr(
        profile_hybrid.VerifiedProfileHybridDetector,
        "_generate_one_page_sources_in_process",
        fake_generate,
    )

    source_worker.run(request, result)
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["memory_boundary"] == "top_level_python_per_page"
    assert payload["sr_image"] == str(sr)
    assert payload["current_omr"] == str(omr)
    assert payload["historical_detector_artifact_runtime_input"] is False
