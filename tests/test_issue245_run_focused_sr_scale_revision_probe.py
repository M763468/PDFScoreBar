from pathlib import Path

import pytest

from tools.issue245.run_focused_sr_scale_revision_probe import (
    _classify_target,
    _container_image_path,
    _container_runtime_env,
    _container_user,
    _container_workspace_path,
    _reference_band_present,
    _sr_weight_mounts,
    _unique_pages,
)


def test_unique_pages_deduplicates_multiple_targets_on_one_page() -> None:
    paths = {
        "fresh_baseline": "/repo/baseline.json",
        "current_sr": "/repo/current_sr.json",
        "historical_sr": "/repo/historical_sr.json",
        "current_omr": "/repo/current_omr.json",
    }
    report = {
        "targets": [
            {
                "score": "ScoreB",
                "page": "page_004",
                "reference": [10, 100, 14, 200],
                "paths": paths,
            },
            {
                "score": "ScoreB",
                "page": "page_004",
                "reference": [20, 100, 24, 200],
                "paths": paths,
            },
            {
                "score": "ScoreA",
                "page": "page_001",
                "reference": [30, 300, 34, 400],
                "paths": paths,
            },
        ]
    }

    pages = _unique_pages(report)

    assert [(page["score"], page["page"]) for page in pages] == [
        ("ScoreA", "page_001"),
        ("ScoreB", "page_004"),
    ]
    assert pages[1]["references"] == [
        [10, 100, 14, 200],
        [20, 100, 24, 200],
    ]


def test_reference_band_requires_exact_row_stat_geometry() -> None:
    reference = (10, 100, 14, 200)

    assert _reference_band_present([(20, 100, 24, 200)], reference) is True
    assert _reference_band_present([(20, 150, 24, 200)], reference) is False


@pytest.mark.parametrize(
    ("x2", "x4", "historical_x4", "expected"),
    [
        (False, True, True, "sr_scale_regression_confirmed"),
        (False, False, True, "current_evaluator_source_regression"),
        (True, True, True, "saved_current_artifact_or_runtime_mismatch"),
        (False, False, False, "unresolved"),
    ],
)
def test_classify_target(
    x2: bool,
    x4: bool,
    historical_x4: bool,
    expected: str,
) -> None:
    assert (
        _classify_target(
            current_x2_present=x2,
            current_x4_present=x4,
            historical_source_x4_present=historical_x4,
        )
        == expected
    )


def test_container_image_path_requires_image_below_main_repo(tmp_path: Path) -> None:
    main_repo = tmp_path / "repo"
    image = main_repo / "data" / "evaluation2" / "images" / "Score" / "page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    assert _container_image_path(main_repo, image) == (
        "/workspace/data/evaluation2/images/Score/page_001.png"
    )

    outside = tmp_path / "outside.png"
    outside.write_bytes(b"image")
    with pytest.raises(ValueError):
        _container_image_path(main_repo, outside)


def test_container_workspace_path_requires_output_below_worktree(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    output = worktree / "logs" / "issue245" / "probe"
    output.mkdir(parents=True)

    assert _container_workspace_path(worktree, output) == "/workspace/logs/issue245/probe"

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        _container_workspace_path(worktree, outside)


def test_sr_weight_mounts_are_read_only_for_both_evaluator_sources(
    tmp_path: Path,
) -> None:
    main_repo = tmp_path / "main"
    weights = main_repo / "external" / "realesrgan" / "weights"
    weights.mkdir(parents=True)
    for filename in ("RealESRGAN_x2plus.pth", "RealESRGAN_x4plus.pth"):
        (weights / filename).write_bytes(b"weights")

    assert _sr_weight_mounts(main_repo, None) == [
        "-v",
        f"{weights}:/workspace/external/realesrgan/weights:ro",
    ]
    historical_snapshot = tmp_path / "historical"
    assert _sr_weight_mounts(main_repo, historical_snapshot) == [
        "-v",
        f"{weights}:/workspace/external/realesrgan/weights:ro",
        "-v",
        f"{weights}:/historical/external/realesrgan/weights:ro",
    ]
    assert (historical_snapshot / "external" / "realesrgan" / "weights").is_dir()


def test_sr_weight_mounts_require_both_scales(tmp_path: Path) -> None:
    main_repo = tmp_path / "main"
    weights = main_repo / "external" / "realesrgan" / "weights"
    weights.mkdir(parents=True)
    (weights / "RealESRGAN_x2plus.pth").write_bytes(b"weights")

    with pytest.raises(FileNotFoundError, match="RealESRGAN_x4plus"):
        _sr_weight_mounts(main_repo, None)


def test_container_user_is_current_uid_and_gid() -> None:
    uid, gid = _container_user().split(":")

    assert uid.isdigit()
    assert gid.isdigit()


def test_container_runtime_env_has_a_resolvable_user_and_writable_cache() -> None:
    assert _container_runtime_env() == [
        "-e",
        "HOME=/tmp",
        "-e",
        "LOGNAME=issue245",
        "-e",
        "USER=issue245",
        "-e",
        "XDG_CACHE_HOME=/tmp",
    ]
