from pathlib import Path

from tools.verification.gt_preparation import apply_candidate_filter_from_inventory as filter_tool


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mask")
    return path


def test_resolve_clef_mask_rejects_explicit_staff_mask_and_uses_semantic_fallback(
    tmp_path: Path,
) -> None:
    staff = _touch(tmp_path / "page_004_proxy_debug_3_staff.png")
    clef = _touch(tmp_path / "page_004_proxy_debug_7_clefs_keys.png")

    resolved = filter_tool._resolve_clef_mask_path(
        {
            "page": "page_004",
            "staff_mask": str(staff),
            "clef_mask": str(staff),
        }
    )

    assert resolved == clef


def test_resolve_clef_mask_keeps_distinct_explicit_mask(tmp_path: Path) -> None:
    staff = _touch(tmp_path / "page_004_proxy_debug_3_staff.png")
    explicit_clef = _touch(tmp_path / "custom_clef_mask.png")
    _touch(tmp_path / "page_004_proxy_debug_7_clefs_keys.png")

    resolved = filter_tool._resolve_clef_mask_path(
        {
            "page": "page_004",
            "staff_mask": str(staff),
            "clef_mask": str(explicit_clef),
        }
    )

    assert resolved == explicit_clef


def test_resolve_clef_mask_returns_none_when_only_staff_mask_exists(tmp_path: Path) -> None:
    staff = _touch(tmp_path / "page_004_proxy_debug_3_staff.png")

    resolved = filter_tool._resolve_clef_mask_path(
        {
            "page": "page_004",
            "staff_mask": str(staff),
            "clef_mask": str(staff),
        }
    )

    assert resolved is None
