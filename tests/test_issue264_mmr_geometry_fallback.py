from __future__ import annotations

import pytest

from src.pipeline.mmr_geometry_layout import (
    require_compatible_mmr_layout,
    select_mmr_numbering_payload,
)


def _payload(counts: list[int], *, marker: str) -> dict:
    return {
        "marker": marker,
        "pages": [
            {
                "page_number": 1,
                "width": 100,
                "height": 200,
                "systems": [
                    {
                        "staves": [],
                        "measures": [
                            {"number": index + 1, "bbox": [index, 0, index + 1, 10]}
                            for index in range(count)
                        ],
                    }
                    for count in counts
                ],
            }
        ],
    }


def test_select_mmr_geometry_prefers_fresh_candidate_when_indices_match() -> None:
    base = _payload([5, 7, 3], marker="base")
    candidate = _payload([5, 7, 3], marker="fresh")

    selected, decision = select_mmr_numbering_payload(
        base,
        candidate,
        page_id="page_042",
    )

    assert selected is candidate
    assert decision == {
        "layout_compatible": True,
        "base_layout_signature": [[5, 7, 3]],
        "candidate_layout_signature": [[5, 7, 3]],
        "numbering_geometry_source": "fresh_current_homr",
        "fallback_reason": None,
    }


def test_select_mmr_geometry_falls_back_to_phase_a_on_index_drift() -> None:
    base = _payload([4, 4, 3, 4, 4, 4, 3, 4, 4], marker="base")
    candidate = _payload([4, 4, 3, 4, 4, 4, 4, 4], marker="fresh")

    selected, decision = select_mmr_numbering_payload(
        base,
        candidate,
        page_id="page_013",
    )

    assert selected is base
    assert decision == {
        "layout_compatible": False,
        "base_layout_signature": [[4, 4, 3, 4, 4, 4, 3, 4, 4]],
        "candidate_layout_signature": [[4, 4, 3, 4, 4, 4, 4, 4]],
        "numbering_geometry_source": "phase_a_base_fallback",
        "fallback_reason": "index_layout_mismatch",
    }

    # The strict helper remains available so callers/tests can explicitly assert
    # incompatibility; production handoff now converts that condition into the
    # provenance-recorded safe fallback above.
    with pytest.raises(RuntimeError, match="changed the numbering index layout"):
        require_compatible_mmr_layout(base, candidate, page_id="page_013")
