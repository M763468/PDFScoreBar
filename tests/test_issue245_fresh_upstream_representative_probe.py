from pathlib import Path

import pytest

from tools.issue245 import run_fresh_upstream_representative_probe as probe


def create_historical_detection(root: Path, run_name: str) -> Path:
    path = (
        root
        / "logs"
        / "hybrid_pipeline_bench"
        / run_name
        / "baseline"
        / "page_001"
        / "page_001_detections.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_normalize_artifact_key_ignores_separator_variants() -> None:
    assert probe.normalize_artifact_key("Va__Prokofiev-Symphony5_page_015") == (
        "vaprokofievsymphony5page015"
    )


def test_resolve_historical_detection_uses_image_key_and_batch_date(
    tmp_path: Path,
) -> None:
    run_name = (
        "eval2_Sibelius_Violin-Concerto__Viola_page_002_20260131_114233"
    )
    path = create_historical_detection(tmp_path, run_name)

    run_dir, detection = probe.resolve_historical_detection(
        tmp_path,
        Path("data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_002.png"),
        "20260131",
    )

    assert run_dir.name == run_name
    assert detection == path


def test_resolve_historical_detection_rejects_ambiguous_batch_matches(
    tmp_path: Path,
) -> None:
    for timestamp in ("103421", "114233"):
        create_historical_detection(
            tmp_path,
            f"eval2_score_page_001_20260131_{timestamp}",
        )

    with pytest.raises(RuntimeError, match="Expected one retained historical detection"):
        probe.resolve_historical_detection(
            tmp_path,
            Path("data/evaluation2/images/score/page_001.png"),
            "20260131",
        )


def test_find_single_detection_accepts_nested_evaluator_output(tmp_path: Path) -> None:
    path = tmp_path / "run" / "page_002" / "page_002_detections.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")

    assert probe.find_single_detection(tmp_path) == path
