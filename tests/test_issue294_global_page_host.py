from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.issue294.run_downstream_candidate_matrix_global_host import _resolve_global_page


def _fake_specs(root: Path):
    specs = []
    for index in range(1, 69):
        score = "Score-A" if index < 45 else "Score-B"
        physical = index if index < 45 else index - 41
        image = root / score / f"page_{physical:03d}.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"png")
        specs.append(
            SimpleNamespace(
                page_id=f"page_{index:03d}",
                global_index=index - 1,
                score=score,
                page_name=f"page_{physical:03d}",
                image_stem=f"{score}_page_{physical:03d}",
                image=image,
            )
        )
    return specs


def test_resolve_global_page_uses_canonical_mapping(tmp_path: Path, monkeypatch) -> None:
    module = types.ModuleType("tools.issue264.run_phase_c_mmr_regression")
    module.build_page_specs = lambda: _fake_specs(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools.issue264.run_phase_c_mmr_regression", module)

    resolved = _resolve_global_page("page_045")

    assert resolved["global_page_id"] == "page_045"
    assert resolved["global_index"] == 44
    assert resolved["score"] == "Score-B"
    assert resolved["page_name"] == "page_004"
    assert resolved["physical_page"] == "004"
    assert resolved["image"].endswith("Score-B/page_004.png")


@pytest.mark.parametrize("page_id", ["045", "page_000", "page_069", "page_45"])
def test_resolve_global_page_rejects_noncanonical_id(page_id: str) -> None:
    with pytest.raises(ValueError):
        _resolve_global_page(page_id)
