from pathlib import Path

from tools.issue245.collect_local_homr_provenance import (
    deduplicate_paths,
    extract_reference_lines,
    model_file_relevant,
    within_window,
)


def test_extract_reference_lines_keeps_model_provenance_only() -> None:
    content = """
plain_value = 1
segnet_path_onnx = base / "segnet_301.onnx"
weights_url = "https://example.invalid/checkpoint.zip"
other = "ignored"
"""

    assert extract_reference_lines(content) == [
        'segnet_path_onnx = base / "segnet_301.onnx"',
        'weights_url = "https://example.invalid/checkpoint.zip"',
    ]


def test_historical_window_is_inclusive() -> None:
    after = "2026-01-01T00:00:00+09:00"
    before = "2026-01-31T23:59:59+09:00"

    assert within_window(after, after=after, before=before)
    assert within_window(before, after=after, before=before)
    assert not within_window(
        "2026-02-01T00:00:00+09:00", after=after, before=before
    )


def test_model_file_filter_limits_shared_cache_scan() -> None:
    assert model_file_relevant(Path("segnet_303.onnx"), broad_repo_scan=False)
    assert model_file_relevant(Path("other_model.onnx"), broad_repo_scan=True)
    assert not model_file_relevant(Path("other_model.onnx"), broad_repo_scan=False)
    assert model_file_relevant(Path("segnet_notes.txt"), broad_repo_scan=False)
    assert not model_file_relevant(Path("unrelated_notes.txt"), broad_repo_scan=False)


def test_deduplicate_paths_preserves_first_occurrence(tmp_path: Path) -> None:
    root = tmp_path / "homr"

    assert deduplicate_paths([root, root / ".", root]) == [root.resolve()]
