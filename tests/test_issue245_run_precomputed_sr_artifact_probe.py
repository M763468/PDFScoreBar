from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.issue245.run_precomputed_sr_artifact_probe import (
    _classify_target,
    _find_working_image,
    _has_reference_band,
    _image_summary,
    _nearest_provenance_files,
    _path_to_container,
    _row_bands,
    _slug,
)


def _write_png(path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def test_slug_is_stable_for_score_and_page() -> None:
    assert _slug("Sibelius-Violin_Concerto-Viola/page_004") == (
        "sibelius_violin_concerto_viola_page_004"
    )


def test_find_working_image_prefers_named_upscaled_page(tmp_path: Path) -> None:
    detection = tmp_path / "run" / "page_001" / "page_001_detections.json"
    detection.parent.mkdir(parents=True)
    detection.write_text("{}", encoding="utf-8")
    _write_png(detection.parent / "debug.png", (400, 400))
    expected = _write_png(detection.parent / "page_001.png", (800, 1200))

    actual = _find_working_image(
        detection,
        "page_001",
        {"width": 200, "height": 300},
    )

    assert actual == expected


def test_find_working_image_rejects_non_upscaled_only(tmp_path: Path) -> None:
    detection = tmp_path / "run" / "page_001" / "page_001_detections.json"
    detection.parent.mkdir(parents=True)
    detection.write_text("{}", encoding="utf-8")
    _write_png(detection.parent / "page_001.png", (200, 300))

    try:
        _find_working_image(
            detection,
            "page_001",
            {"width": 200, "height": 300},
        )
    except RuntimeError as error:
        assert "Could not select exactly one upscaled" in str(error)
    else:
        raise AssertionError("Expected RuntimeError")


def test_path_to_container_maps_all_supported_roots(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    main_repo = tmp_path / "main"
    worktree_file = worktree / "logs" / "probe.json"
    main_log = main_repo / "logs" / "historical" / "page.png"
    main_data = main_repo / "data" / "evaluation2" / "page.png"
    for path in (worktree_file, main_log, main_data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    assert (
        _path_to_container(worktree_file, worktree=worktree, main_repo=main_repo)
        == "/workspace/logs/probe.json"
    )
    assert (
        _path_to_container(main_log, worktree=worktree, main_repo=main_repo)
        == "/main_logs/historical/page.png"
    )
    assert (
        _path_to_container(main_data, worktree=worktree, main_repo=main_repo)
        == "/main_data/evaluation2/page.png"
    )


def test_reference_band_and_classifications() -> None:
    rows = [{"top": 100, "bottom": 200}]
    reference = (10, 100, 14, 200)
    assert _has_reference_band(rows, reference) is True
    assert (
        _classify_target(control_present=False, historical_pixels_present=True)
        == "historical_sr_pixels_restore"
    )
    assert (
        _classify_target(control_present=False, historical_pixels_present=False)
        == "homr_runtime_or_retained_artifact_postprocess_dependency"
    )


def test_image_summary_records_exact_hash_and_dimensions(tmp_path: Path) -> None:
    image = _write_png(tmp_path / "page.png", (64, 96))
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 1
    try:
        summary = _image_summary(image)
        assert summary["width"] == 64
        assert summary["height"] == 96
        assert summary["format"] == "PNG"
        assert len(summary["sha256"]) == 64
        assert Image.MAX_IMAGE_PIXELS == 1
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def test_nearest_provenance_files_finds_run_metadata(tmp_path: Path) -> None:
    run = tmp_path / "run"
    detection = run / "sr" / "page_001" / "page_001_detections.json"
    detection.parent.mkdir(parents=True)
    detection.write_text("{}", encoding="utf-8")
    config = run / "run_config.json"
    config.write_text(json.dumps({"commit": "abc"}), encoding="utf-8")
    run_sh = run / "run.sh"
    run_sh.write_text("#!/bin/sh\n", encoding="utf-8")

    records = _nearest_provenance_files(detection, max_levels=3)

    assert {Path(record["path"]).name for record in records} == {
        "run_config.json",
        "run.sh",
    }


def test_row_bands_accepts_production_row_stat_schema(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "tools.issue245.run_precomputed_sr_artifact_probe.load_json_boxes",
        lambda _path: [],
    )
    monkeypatch.setattr(
        "tools.issue245.run_precomputed_sr_artifact_probe.apply_hybrid_consensus_filter",
        lambda **_kwargs: [(10, 100, 14, 200)],
    )
    monkeypatch.setattr(
        "tools.issue245.run_precomputed_sr_artifact_probe.build_row_stats",
        lambda *_args, **_kwargs: [{"center": 150.0, "top": 100.0, "bottom": 200.0}],
    )

    rows, hybrid_count = _row_bands(
        baseline_path=tmp_path / "baseline.json",
        sr_path=tmp_path / "sr.json",
        omr_path=tmp_path / "omr.json",
    )

    assert rows == [{"center": 150.0, "top": 100, "bottom": 200}]
    assert hybrid_count == 1
