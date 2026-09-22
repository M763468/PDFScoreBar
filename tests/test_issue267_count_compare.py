from __future__ import annotations

import json
from pathlib import Path

from tools.issue267.compare_numbering_count_signatures import (
    collect_run_signatures,
    compare_signatures,
)


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
