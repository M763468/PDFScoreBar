from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.issue294 import run_downstream_candidate_matrix_global_host as global_host
from tools.issue294 import run_same_original_ab_host as base
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


def _install_fake_specs(tmp_path: Path, monkeypatch) -> None:
    module = types.ModuleType("tools.issue264.run_phase_c_mmr_regression")
    module.build_page_specs = lambda: _fake_specs(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools.issue264.run_phase_c_mmr_regression", module)


def test_resolve_global_page_uses_canonical_mapping(tmp_path: Path, monkeypatch) -> None:
    _install_fake_specs(tmp_path, monkeypatch)

    resolved = _resolve_global_page("page_045")

    assert resolved["global_page_id"] == "page_045"
    assert resolved["global_index"] == 44
    assert resolved["score"] == "Score-B"
    assert resolved["page_name"] == "page_004"
    assert resolved["physical_page"] == "004"
    assert resolved["image"].endswith("Score-B/page_004.png")


def test_global_run_delegates_mapped_score_and_page_then_restores_selectors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_specs(tmp_path, monkeypatch)
    original_score = base.SCORE
    original_allowed = base.ALLOWED_PAGES
    observed: dict[str, object] = {}

    def fake_run(run_tag: str, pages: list[str], latest_commit: str | None):
        observed.update(
            {
                "run_tag": run_tag,
                "pages": list(pages),
                "latest_commit": latest_commit,
                "score": base.SCORE,
                "allowed": set(base.ALLOWED_PAGES),
            }
        )
        return {"matrix_report": "fake/report.json"}

    monkeypatch.setattr(global_host.matrix_host, "run", fake_run)

    result = global_host.run(
        run_tag="risk-page-045",
        global_page="page_045",
        latest_commit="f" * 40,
        resolve_only=False,
    )

    assert observed == {
        "run_tag": "risk-page-045",
        "pages": ["004"],
        "latest_commit": "f" * 40,
        "score": "Score-B",
        "allowed": {"004"},
    }
    assert result["mapping"]["global_page_id"] == "page_045"
    assert result["matrix"] == {"matrix_report": "fake/report.json"}
    assert base.SCORE == original_score
    assert base.ALLOWED_PAGES is original_allowed


@pytest.mark.parametrize("page_id", ["045", "page_000", "page_069", "page_45"])
def test_resolve_global_page_rejects_noncanonical_id(page_id: str) -> None:
    with pytest.raises(ValueError):
        _resolve_global_page(page_id)
