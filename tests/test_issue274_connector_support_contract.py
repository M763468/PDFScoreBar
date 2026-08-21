from pathlib import Path

import pytest

from src.common.connector_artifacts import connector_mask_paths_for_numbering


def _staff_path(root: Path, stem: str = "page_001") -> Path:
    path = root / "baseline" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"staff")
    return path


def test_numbering_fallback_remains_available_without_declared_current_support(
    tmp_path: Path,
) -> None:
    staff = _staff_path(tmp_path / "hybrid")

    assert connector_mask_paths_for_numbering(staff) is None


def test_numbering_rejects_missing_pair_inside_declared_current_support(
    tmp_path: Path,
) -> None:
    hybrid = tmp_path / "hybrid"
    staff = _staff_path(hybrid)
    (hybrid / "current_support").mkdir()

    with pytest.raises(RuntimeError, match="connector semantic pair is missing"):
        connector_mask_paths_for_numbering(staff)
