"""Focused tests for Issue #372 final-numbering semantic comparator."""

from pathlib import Path

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


def test_current_homr_staff_mask_resolves_child_current_support_result(
    tmp_path: Path,
) -> None:
    import json
    from experiments.issue372.run_fresh_downstream_semantic_replay import (
        _current_homr_staff_mask,
    )

    hybrid_root = tmp_path / "hybrid_run"
    hybrid = hybrid_root / "hybrid_results" / "page_001_hybrid.json"
    hybrid.parent.mkdir(parents=True)
    hybrid.write_text("[]")

    source_result = (
        hybrid_root
        / "source_page_workers"
        / "Score"
        / "page_001"
        / "result.json"
    )
    source_result.parent.mkdir(parents=True)
    source_result.write_text(json.dumps({
        "status": "completed",
        "current_sr_detection": str(
            hybrid_root
            / "current_support"
            / "Score"
            / "page_001"
            / "artifacts"
            / "current_homr"
            / "batch"
            / "page_001"
            / "page_001_detections.json"
        ),
    }))

    staff = (
        hybrid_root
        / "current_support"
        / "Score"
        / "page_001"
        / "artifacts"
        / "current_homr"
        / "batch"
        / "page_001"
        / "page_001_staff_mask.png"
    )
    staff.parent.mkdir(parents=True)
    staff.write_bytes(b"mask")

    child_result = (
        hybrid_root
        / "current_support"
        / "Score"
        / "page_001"
        / "result.json"
    )
    child_result.parent.mkdir(parents=True, exist_ok=True)
    child_result.write_text(json.dumps({
        "status": "completed",
        "current_homr_staff_mask": str(staff),
        "historical_detector_artifact_runtime_input": False,
    }))

    resolved = _current_homr_staff_mask(
        {"hybrid_predictions": str(hybrid)},
        score="Score",
        page="page_001",
        issue43_repo_root=tmp_path,
    )

    assert resolved == staff


def test_number_value_reassessment_ignores_empty_system_bookkeeping() -> None:
    from experiments.issue372.reassess_final_numbering_values import (
        compare_number_values,
    )

    left = {
        ("Score", "page_001"): {
            "local_logical": {
                "system_count": 1,
                "empty_system_count": 3,
                "systems": [{"measure_count": 2, "numbers": [1, 2]}],
            },
            "continued_logical": {
                "system_count": 1,
                "empty_system_count": 3,
                "systems": [{"measure_count": 2, "numbers": [10, 11]}],
            },
            "continued_start_number": 10,
            "continued_next_number": 12,
            "mmr_overrides": [],
        }
    }
    right = {
        ("Score", "page_001"): {
            "local_logical": {
                "system_count": 1,
                "empty_system_count": 2,
                "systems": [{"measure_count": 2, "numbers": [1, 2]}],
            },
            "continued_logical": {
                "system_count": 1,
                "empty_system_count": 2,
                "systems": [{"measure_count": 2, "numbers": [10, 11]}],
            },
            "continued_start_number": 10,
            "continued_next_number": 12,
            "mmr_overrides": [],
        }
    }

    report = compare_number_values(left, right)

    assert report["number_value_match"] is True
    assert report["changed_page_count"] == 0


def test_number_value_reassessment_detects_number_change() -> None:
    from experiments.issue372.reassess_final_numbering_values import (
        compare_number_values,
    )

    base = {
        "local_logical": {
            "system_count": 1,
            "empty_system_count": 0,
            "systems": [{"measure_count": 2, "numbers": [1, 2]}],
        },
        "continued_logical": {
            "system_count": 1,
            "empty_system_count": 0,
            "systems": [{"measure_count": 2, "numbers": [10, 11]}],
        },
        "continued_start_number": 10,
        "continued_next_number": 12,
        "mmr_overrides": [],
    }
    changed = {
        **base,
        "continued_logical": {
            "system_count": 1,
            "empty_system_count": 0,
            "systems": [{"measure_count": 2, "numbers": [10, 12]}],
        },
        "continued_next_number": 13,
    }

    report = compare_number_values(
        {("Score", "page_001"): base},
        {("Score", "page_001"): changed},
    )

    assert report["number_value_match"] is False
    assert report["changed_page_count"] == 1
