from __future__ import annotations

import json
from pathlib import Path

from tools.issue267.compare_numbering_count_signatures import (
    collect_run_signatures,
    compare_signatures,
)
from tools.issue267.run_numbering_count_replay import build_page_specs


def _write_numbering(path: Path, counts: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pages": [
            {
                "systems": [
                    {"measures": [{"number": i + 1} for i in range(count)]} for count in counts
                ]
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
    assert report["baseline_total_measures"] == 15
    assert report["candidate_total_measures"] == 15
    assert report["total_measure_delta"] == 0
    assert report["changed_pages"] == []


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
    assert report["total_measure_delta"] == -1
    assert report["changed_pages"] == [
        {
            "page_id": "page_001",
            "baseline": [5, 6],
            "candidate": [5, 5],
            "baseline_total": 11,
            "candidate_total": 10,
        }
    ]


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
