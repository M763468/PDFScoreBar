from pathlib import Path

import pytest

from tools.issue245 import run_fresh_upstream_full68_probe as probe


def test_issue120_page_set_has_68_pages() -> None:
    assert sum(len(pages) for pages in probe.SCORES.values()) == 68


def test_discover_canonical_images_uses_issue120_page_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_root = tmp_path / "images"
    score = image_root / "score_a"
    score.mkdir(parents=True)
    selected = [score / "page_001.png", score / "page_003.png"]
    excluded = score / "page_002.png"
    for path in [*selected, excluded]:
        path.write_bytes(b"image")

    monkeypatch.setattr(
        probe,
        "SCORES",
        {"score_a": ["page_001", "page_003"]},
    )

    assert probe.discover_canonical_images(image_root) == selected


def test_discover_canonical_images_rejects_missing_manifest_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_root = tmp_path / "images"
    image_root.mkdir(parents=True)
    monkeypatch.setattr(probe, "SCORES", {"score_a": ["page_001"]})

    with pytest.raises(RuntimeError, match="image set is incomplete"):
        probe.discover_canonical_images(image_root)


def test_build_inventory_rejects_duplicate_normalized_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_repo = tmp_path
    first = main_repo / "data/evaluation2/images/score-a/page_001.png"
    second = main_repo / "data/evaluation2/images/score_a/page_001.png"
    for path in (first, second):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")

    monkeypatch.setattr(
        probe,
        "resolve_historical_detection",
        lambda *_args: (tmp_path / "run", tmp_path / "detection.json"),
    )

    with pytest.raises(RuntimeError, match="Duplicate normalized artifact key"):
        probe.build_inventory(main_repo, [first, second], "20260131")


def test_aggregate_results_sums_completed_pages_and_lists_failures() -> None:
    comparison = {
        "left": {"count": 10, "thin_barline_tagged_count": 2},
        "right": {"count": 11, "thin_barline_tagged_count": 3},
        "matched_count": 9,
        "left_only": {"count": 1, "thin_barline_tagged_count": 0},
        "right_only": {"count": 2, "thin_barline_tagged_count": 1},
        "semantic_equal": False,
    }
    pages = [
        {
            "artifact_key": "page_a",
            "status": "completed",
            "comparison": comparison,
        },
        {
            "artifact_key": "page_b",
            "status": "failed",
            "error": "boom",
        },
    ]

    aggregate = probe.aggregate_results(pages)

    assert aggregate == {
        "pages_completed": 1,
        "pages_failed": 1,
        "pages_semantic_equal": 0,
        "pages_different": 1,
        "historical_count": 10,
        "candidate_count": 11,
        "matched_count": 9,
        "historical_only_count": 1,
        "candidate_only_count": 2,
        "historical_thin_barline_tagged_count": 2,
        "candidate_thin_barline_tagged_count": 3,
        "failed_artifact_keys": ["page_b"],
        "differing_artifact_keys": ["page_a"],
    }
