"""Focused tests for Issue #372 final-numbering semantic comparator."""

from experiments.issue372.compare_final_numbering_semantics import compare


def _page(*, counts, numbers, geometry=None, next_number=None):
    if geometry is None:
        geometry = [[None] * count for count in counts]
    return {
        "system_count": len(counts),
        "measure_counts": list(counts),
        "number_sequences": numbers,
        "measure_geometry": geometry,
        "empty_system_count": 0,
        "metadata": {
            "start_number": 1,
            "next_number": next_number,
            "movement_boundaries": [],
        },
    }


def test_geometry_only_change_does_not_fail_logical_gate() -> None:
    baseline = {
        "page_000": _page(
            counts=[2],
            numbers=[[1, 2]],
            geometry=[[[0, 0, 10, 10], [10, 0, 20, 10]]],
            next_number=3,
        )
    }
    candidate = {
        "page_000": _page(
            counts=[2],
            numbers=[[1, 2]],
            geometry=[[[1, 0, 11, 10], [11, 0, 21, 10]]],
            next_number=3,
        )
    }

    report = compare(baseline, candidate)

    assert report["logical_numbering_match"] is True
    assert report["geometry_only_changed_page_count"] == 1
    assert report["logical_changed_page_count"] == 0


def test_measure_number_sequence_change_fails_logical_gate() -> None:
    baseline = {
        "page_000": _page(counts=[2], numbers=[[1, 2]], next_number=3)
    }
    candidate = {
        "page_000": _page(counts=[2], numbers=[[1, 3]], next_number=4)
    }

    report = compare(baseline, candidate)

    assert report["logical_numbering_match"] is False
    assert report["logical_changed_page_count"] == 1


def test_measure_count_change_fails_logical_gate() -> None:
    baseline = {
        "page_000": _page(counts=[2], numbers=[[1, 2]], next_number=3)
    }
    candidate = {
        "page_000": _page(counts=[3], numbers=[[1, 2, 3]], next_number=4)
    }

    report = compare(baseline, candidate)

    assert report["logical_numbering_match"] is False
    assert report["logical_changed_page_count"] == 1


def test_fresh_downstream_d27_delta_reconstruction_preserves_list_semantics() -> None:
    from experiments.issue372.run_fresh_downstream_semantic_replay import (
        apply_acceptance_deltas,
    )

    control = [
        (10, 0, 14, 100),
        (20, 0, 24, 100),
        (20, 0, 24, 100),
    ]
    deltas = [
        {
            "bbox": [10, 0, 14, 100],
            "control_accept": True,
            "clean_accept": False,
        },
        {
            "bbox": [30, 0, 34, 100],
            "control_accept": False,
            "clean_accept": True,
        },
    ]

    assert apply_acceptance_deltas(control, deltas) == [
        (20, 0, 24, 100),
        (20, 0, 24, 100),
        (30, 0, 34, 100),
    ]
