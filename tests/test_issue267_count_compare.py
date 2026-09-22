from __future__ import annotations

import json
from pathlib import Path

from tools.issue267.compare_numbering_count_signatures import (
    collect_run_signatures,
    compare_signatures,
)
from tools.issue267.run_numbering_count_replay import build_page_specs


def _write_numbering(
    path: Path,
    counts: list[int],
    *,
    measure_x_offset: int = 0,
    empty_systems: list[dict] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    systems = []
    for system_index, count in enumerate(counts):
        y1 = 100 * system_index
        y2 = y1 + 80
        systems.append(
            {
                "staves": [{"bbox": [0, y1, 1000, y2]}],
                "measures": [
                    {
                        "number": measure_index + 1,
                        "bbox": [
                            measure_x_offset + measure_index * 100,
                            y1,
                            measure_x_offset + (measure_index + 1) * 100,
                            y2,
                        ],
                    }
                    for measure_index in range(count)
                ],
            }
        )
    payload = {
        "pages": [
            {
                "systems": systems,
                "empty_systems": empty_systems or [],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_issue267_count_comparator_reports_exact_match(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    for run_dir in (baseline, candidate):
        _write_numbering(
            run_dir / "intermediate" / "page_001" / "numbering_base.json",
            [5, 6],
        )
        _write_numbering(
            run_dir / "intermediate" / "page_002" / "numbering_base.json",
            [4],
        )

    report = compare_signatures(
        collect_run_signatures(baseline),
        collect_run_signatures(candidate),
    )

    assert report["exact_match"] is True
    assert report["count_match"] is True
    assert report["semantic_match"] is True
    assert report["baseline_total_measures"] == 15
    assert report["candidate_total_measures"] == 15
    assert report["total_measure_delta"] == 0
    assert report["count_changed_pages"] == []
    assert report["geometry_changed_pages"] == []


def test_issue267_count_comparator_identifies_changed_page(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_numbering(
        baseline / "intermediate" / "page_001" / "numbering_base.json",
        [5, 6],
    )
    _write_numbering(
        candidate / "intermediate" / "page_001" / "numbering_base.json",
        [5, 5],
    )

    report = compare_signatures(
        collect_run_signatures(baseline),
        collect_run_signatures(candidate),
    )

    assert report["exact_match"] is False
    assert report["count_match"] is False
    assert report["semantic_match"] is False
    assert report["total_measure_delta"] == -1
    assert len(report["count_changed_pages"]) == 1
    changed = report["count_changed_pages"][0]
    assert changed["page_id"] == "page_001"
    assert changed["baseline_counts"] == [5, 6]
    assert changed["candidate_counts"] == [5, 5]
    assert changed["baseline_total"] == 11
    assert changed["candidate_total"] == 10


def test_issue267_comparator_detects_boundary_shift_with_same_counts(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_numbering(
        baseline / "intermediate" / "page_001" / "numbering_base.json",
        [2],
    )
    _write_numbering(
        candidate / "intermediate" / "page_001" / "numbering_base.json",
        [2],
        measure_x_offset=1,
    )

    report = compare_signatures(
        collect_run_signatures(baseline),
        collect_run_signatures(candidate),
    )

    assert report["exact_match"] is True
    assert report["count_match"] is True
    assert report["semantic_match"] is False
    assert report["total_measure_delta"] == 0
    assert report["count_changed_pages"] == []
    assert report["geometry_changed_pages"][0]["baseline_counts"] == [2]
    assert report["geometry_changed_pages"][0]["candidate_counts"] == [2]


def test_issue267_comparator_detects_empty_system_change(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_numbering(
        baseline / "intermediate" / "page_001" / "numbering_base.json",
        [2],
        empty_systems=[{"staves": [{"bbox": [0, 300, 1000, 380]}], "reason": "no_measures"}],
    )
    _write_numbering(
        candidate / "intermediate" / "page_001" / "numbering_base.json",
        [2],
    )

    report = compare_signatures(
        collect_run_signatures(baseline),
        collect_run_signatures(candidate),
    )

    assert report["exact_match"] is True
    assert report["count_match"] is True
    assert report["semantic_match"] is False
    assert report["total_measure_delta"] == 0
    assert report["count_changed_pages"] == []
    assert len(report["geometry_changed_pages"]) == 1


def test_issue267_replay_resolves_accepted_retained_inputs(tmp_path: Path) -> None:
    page_index = tmp_path / "logs/issue94_mmr_current_state/page_inputs.json"
    page_index.parent.mkdir(parents=True)
    page_index.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_id": "page_001",
                        "image": "/legacy/path/TestScore_page_001.png",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    specs = build_page_specs(
        tmp_path,
        support_run="issue264_phase_c_current_production_full68_02",
        page_limit=1,
    )

    assert len(specs) == 1
    spec = specs[0]
    assert spec.page_id == "page_001"
    assert spec.score == "TestScore"
    assert spec.page_name == "page_001"
    assert spec.image == tmp_path / "data/evaluation2/images/TestScore/page_001.png"
    assert spec.barlines == (
        tmp_path
        / "logs/verification/detector_full68"
        / "issue255_production_restore_full68_top_level_worker_01"
        / "production_runs/TestScore"
        / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction"
        / "probe_rescue_candidates/eval2_TestScore_page_001"
        / "pipeline2_no_peak_filtered_cnn.json"
    )
    assert spec.staff_mask == (
        tmp_path
        / "logs/issue264_phase_c_mmr_regression"
        / "issue264_phase_c_current_production_full68_02"
        / "phase_a_hybrid_replay/TestScore/sr/batch/page_001"
        / "page_001_proxy_debug_3_staff.png"
    )
