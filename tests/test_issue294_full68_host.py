from __future__ import annotations

from tools.issue294.run_downstream_candidate_matrix_full68_host import (
    _aggregate_gates,
    _chunk_mappings,
)


def _mapping(page: int, score: str, physical: int) -> dict[str, object]:
    return {
        "global_page_id": f"page_{page:03d}",
        "score": score,
        "page_name": f"page_{physical:03d}",
        "physical_page": f"{physical:03d}",
    }


def test_chunk_mappings_preserves_order_and_score_boundaries() -> None:
    mappings = [
        _mapping(1, "score-a", 1),
        _mapping(2, "score-a", 2),
        _mapping(3, "score-a", 3),
        _mapping(4, "score-b", 1),
        _mapping(5, "score-b", 2),
    ]

    chunks = _chunk_mappings(mappings, 2)

    assert [[item["global_page_id"] for item in chunk] for chunk in chunks] == [
        ["page_001", "page_002"],
        ["page_003"],
        ["page_004", "page_005"],
    ]
    assert all(len({item["score"] for item in chunk}) == 1 for chunk in chunks)


def _page_summary(*, b_pass: bool = True, c_pass: bool = True) -> dict[str, object]:
    return {
        "B_full_vs_detector_material": {
            "full_count": 12,
            "detector_material_count": 12,
            "boxes_exact": True,
        },
        "candidate_native_geometry": {
            "B_vs_A": {"count_topology_numbering_pass": b_pass},
            "C_vs_A": {"count_topology_numbering_pass": c_pass},
            "B_C_final_barlines_exact": True,
            "B_C_numbering_exact": True,
        },
    }


def test_aggregate_gates_requires_every_page_to_pass() -> None:
    pages = [_page_summary(), _page_summary()]

    assert _aggregate_gates(pages) == {
        "B_b377": True,
        "C_latest": True,
        "B_detector_material_matches_full_B_all_pages": True,
        "B_C_native_final_barlines_identical_all_pages": True,
        "B_C_native_numbering_identical_all_pages": True,
    }

    pages[1] = _page_summary(c_pass=False)
    assert _aggregate_gates(pages)["B_b377"] is True
    assert _aggregate_gates(pages)["C_latest"] is False
