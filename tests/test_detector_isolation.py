from pathlib import Path

from src.pipeline.detection import isolation
from src.pipeline.detection.input_contract import build_detector_input_contract
from src.pipeline.core.run_ids import build_probe_run_id


def _config() -> dict:
    return {
        "detection": {
            "execution_mode": "isolated_per_page",
            "detector_route": "dense_full_pipeline",
            "homr_profile": "stage_e_verified",
            "enable_sr": True,
            "sr_scale": 4,
            "probe_use_original_images": True,
        }
    }


def test_isolated_detector_aggregates_page_outputs(tmp_path: Path, monkeypatch) -> None:
    score = tmp_path / "Score"
    score.mkdir()
    images = [score / "page_001.png", score / "page_002.png"]
    for image in images:
        image.write_bytes(b"image")

    calls: list[Path] = []
    config = _config()
    contract = build_detector_input_contract(config["detection"])

    def fake_page_worker(*, image: Path, run_id: str, page_root: Path, **_kwargs):
        calls.append(image)
        probe_root = page_root / "child_probe"
        probe_page = probe_root / build_probe_run_id(image)
        probe_page.mkdir(parents=True)
        (probe_page / "pipeline2_no_peak_filtered_cnn.json").write_text("[]\n")

        hybrid_root = page_root / "child_hybrid"
        baseline = hybrid_root / "baseline" / "batch" / image.stem
        baseline.mkdir(parents=True)
        (baseline / f"{image.stem}_proxy_debug_3_staff.png").write_bytes(b"mask")
        hybrid = hybrid_root / "hybrid_results" / f"{image.stem}_hybrid.json"
        hybrid.parent.mkdir(parents=True)
        hybrid.write_text("[]\n")
        return {
            "status": "completed",
            "commands": [["page-worker", str(image)]],
            "hybrid_output_dir": str(hybrid_root),
            "probe_output_dir": str(probe_root),
            "detector_input_contract": contract,
            "detector_route": "dense_full_pipeline",
            "homr_profile": "stage_e_verified",
            "run_id": run_id,
        }

    monkeypatch.setattr(isolation, "_run_page_worker", fake_page_worker)

    run_dir = tmp_path / "run"
    result = isolation.run_detection_isolated_per_page(
        config,
        images,
        ["page_001", "page_002"],
        "test",
        run_dir,
        dry_run=False,
    )

    assert calls == images
    assert result["execution_mode"] == "isolated_per_page"
    assert result["detector_input_contract"] == contract
    assert len(result["page_runs"]) == 2
    assert (run_dir / "intermediate/detector_input_contract.json").is_file()

    aggregate_probe = Path(result["probe_output_dir"])
    for image in images:
        assert (
            aggregate_probe
            / build_probe_run_id(image)
            / "pipeline2_no_peak_filtered_cnn.json"
        ).is_file()

    aggregate_hybrid = Path(result["hybrid_output_dir"])
    for image in images:
        assert (
            aggregate_hybrid
            / "baseline"
            / "batch"
            / image.stem
            / f"{image.stem}_proxy_debug_3_staff.png"
        ).is_file()
        assert (aggregate_hybrid / "hybrid_results" / f"{image.stem}_hybrid.json").is_file()


def test_isolated_detector_rejects_in_memory_images(tmp_path: Path) -> None:
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir()
    image.write_bytes(b"image")

    try:
        isolation.run_detection_isolated_per_page(
            _config(),
            [image],
            ["page_001"],
            "test",
            tmp_path / "run",
            dry_run=False,
            in_memory_images={"page_001": object()},
        )
    except ValueError as error:
        assert "persisted image files" in str(error)
    else:
        raise AssertionError("Expected in-memory image rejection")
