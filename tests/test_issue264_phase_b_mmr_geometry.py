from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.mmr_geometry_handoff import build_mmr_page_context


def test_mmr_handoff_reuses_current_x4_support_without_rebuilding_numbering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_path = tmp_path / "numbering_base.json"
    staff_mask = tmp_path / "current_staff_mask.png"
    base_path.write_text("{}\n", encoding="utf-8")
    staff_mask.write_bytes(b"staff")

    page_ctx = {
        "page_001": {
            "numbering_base": base_path,
            "intermediate_dir": tmp_path,
            "resolved": {
                "staff_mask": "proxy_staff.png",
                "current_homr_staff_mask": str(staff_mask),
            },
        }
    }
    captured: dict[str, Path] = {}

    def fake_build_mmr_support(
        *,
        numbering_base_path: Path,
        current_homr_staff_mask: Path,
        output_path: Path,
    ) -> dict:
        captured["numbering_base_path"] = numbering_base_path
        captured["current_homr_staff_mask"] = current_homr_staff_mask
        captured["output_path"] = output_path
        return {"provenance": {"source": "current_x4_support"}}

    monkeypatch.setattr(
        "src.pipeline.mmr_geometry_handoff.build_mmr_support",
        fake_build_mmr_support,
    )

    mmr_ctx = build_mmr_page_context(object(), ["page_001"], set(), page_ctx)

    assert captured == {
        "numbering_base_path": base_path,
        "current_homr_staff_mask": staff_mask,
        "output_path": tmp_path / "mmr_support.json",
    }
    assert page_ctx["page_001"]["numbering_base"] == base_path
    assert page_ctx["page_001"]["resolved"]["staff_mask"] == "proxy_staff.png"
    assert mmr_ctx["page_001"]["numbering_base"] == base_path
    assert mmr_ctx["page_001"]["mmr_support"] == tmp_path / "mmr_support.json"
    assert mmr_ctx["page_001"]["resolved"]["mmr_support"] == {"source": "current_x4_support"}


def test_mmr_handoff_requires_declared_current_homr_staff_mask(tmp_path: Path) -> None:
    base_path = tmp_path / "numbering_base.json"
    base_path.write_text("{}\n", encoding="utf-8")
    page_ctx = {
        "page_001": {
            "numbering_base": base_path,
            "intermediate_dir": tmp_path,
            "resolved": {"staff_mask": "proxy_staff.png"},
        }
    }

    with pytest.raises(
        FileNotFoundError,
        match="Dense MMR support requires current-HOMR staff mask for page_001",
    ):
        build_mmr_page_context(object(), ["page_001"], set(), page_ctx)


def test_mmr_handoff_skips_excluded_or_missing_numbering_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    page_ctx = {
        "page_001": {
            "numbering_base": tmp_path / "excluded_numbering.json",
            "intermediate_dir": tmp_path / "page_001",
            "resolved": {},
        },
        "page_002": {
            "numbering_base": tmp_path / "missing_numbering.json",
            "intermediate_dir": tmp_path / "page_002",
            "resolved": {},
        },
    }

    monkeypatch.setattr(
        "src.pipeline.mmr_geometry_handoff.build_mmr_support",
        lambda **_kwargs: pytest.fail("MMR support should not be built for skipped pages"),
    )

    mmr_ctx = build_mmr_page_context(
        object(),
        ["page_001", "page_002"],
        {"page_001"},
        page_ctx,
    )

    assert "mmr_support" not in mmr_ctx["page_001"]
    assert "mmr_support" not in mmr_ctx["page_002"]
