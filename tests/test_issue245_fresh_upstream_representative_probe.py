from pathlib import Path

import pytest

from tools.issue245 import run_fresh_upstream_representative_probe as probe


def test_resolve_single_glob_returns_unique_file(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "logs"
        / "hybrid_pipeline_bench"
        / "eval2_score_page_001_run"
        / "baseline"
        / "page_001"
        / "page_001_detections.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")

    result = probe.resolve_single_glob(
        tmp_path,
        "logs/hybrid_pipeline_bench/eval2_score_page_001_*/baseline/**/page_*_detections.json",
    )

    assert result == path


def test_resolve_single_glob_rejects_ambiguous_matches(tmp_path: Path) -> None:
    for name in ("run_a", "run_b"):
        path = (
            tmp_path
            / "logs"
            / "hybrid_pipeline_bench"
            / name
            / "baseline"
            / "page_001_detections.json"
        )
        path.parent.mkdir(parents=True)
        path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Expected one file"):
        probe.resolve_single_glob(
            tmp_path,
            "logs/hybrid_pipeline_bench/*/baseline/**/page_*_detections.json",
        )


def test_find_single_detection_accepts_nested_evaluator_output(tmp_path: Path) -> None:
    path = tmp_path / "run" / "page_002" / "page_002_detections.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")

    assert probe.find_single_detection(tmp_path) == path
