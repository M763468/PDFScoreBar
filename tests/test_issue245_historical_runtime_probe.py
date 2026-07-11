from __future__ import annotations

from pathlib import Path

from tools.issue245 import run_historical_runtime_probe as probe


def test_historical_mask_path_uses_detection_stem(tmp_path: Path) -> None:
    detection = tmp_path / "page_001_detections.json"

    assert probe.historical_mask_path(detection, "staff_mask") == (
        tmp_path / "page_001_staff_mask.png"
    )


def test_iter_model_files_filters_suffix_and_name(tmp_path: Path) -> None:
    matching = tmp_path / "cache/segnet_model.onnx"
    matching.parent.mkdir(parents=True)
    matching.write_bytes(b"model")
    (tmp_path / "cache/unrelated.onnx").write_bytes(b"other")
    (tmp_path / "cache/segnet_model.txt").write_text("not a model", encoding="utf-8")

    assert list(probe.iter_model_files([tmp_path])) == [matching.resolve()]


def test_runtime_provenance_without_git_uses_host_metadata_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(probe, "IMPORT_CHECKS", ())
    monkeypatch.setattr(probe, "PROVENANCE_ENV_KEYS", ())
    monkeypatch.setattr(probe, "package_versions", lambda: {})
    monkeypatch.setattr(probe, "runtime_provider_summary", lambda: {})

    result = probe.runtime_provenance_without_git(tmp_path, [])

    assert result["git"] == {
        "available": False,
        "reason": "disabled in container; host metadata is supplied via environment",
    }
    assert result["images"] == []
    assert result["runtime"]["repo_root"] == str(tmp_path)
