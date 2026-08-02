import json
from pathlib import Path

import tools.issue255.analyze_focused_candidate_multiplicity as multiplicity
from tools.issue255.analyze_focused_candidate_multiplicity import (
    Policy,
    _accepted_root_collisions,
    _simulate_policy,
    _stable_match_details,
)


def test_stable_match_locks_exact_baseline_before_approximate_addition() -> None:
    reference = [(10, 20, 14, 120)]
    current = [
        (11, 20, 15, 120),
        (10, 20, 14, 120),
    ]

    details = _stable_match_details(reference, current)

    assert details["tp"] == 1
    assert details["fp"] == 1
    assert details["matches"] == [
        {
            "prediction_index": 1,
            "reference_index": 0,
            "prediction": [10, 20, 14, 120],
            "reference": [10, 20, 14, 120],
            "iou": 1.0,
            "exact": True,
        }
    ]
    assert details["false_positive_boxes"] == [[11, 20, 15, 120]]


def test_policy_preserves_baseline_and_recovers_new_target_without_fp() -> None:
    accepted = [
        (10, 20, 14, 120),
        (100, 20, 104, 120),
    ]
    baseline = [(10, 20, 14, 120)]
    duplicate = (11, 20, 15, 120)
    recovery = (100, 20, 104, 120)
    current = [baseline[0], duplicate, recovery]

    result = _simulate_policy(
        accepted=accepted,
        baseline=baseline,
        current=current,
        scores={duplicate: 0.99, recovery: 0.98},
        targets=[accepted[1]],
        policy=Policy(
            x_tolerance=2,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
        include_details=True,
    )

    assert result["metrics"] == {"tp": 2, "fp": 0, "fn": 0}
    assert result["all_targets_recovered"] is True
    assert result["suppressed_count"] == 1
    assert result["suppressed"][0]["candidate_bbox"] == list(duplicate)
    assert result["accepted_collision_count"] == 0


def test_policy_reports_collision_between_distinct_accepted_barlines() -> None:
    accepted = [
        (10, 20, 14, 120),
        (15, 20, 19, 120),
    ]
    baseline = [accepted[0]]
    current = [accepted[0], accepted[1]]

    result = _simulate_policy(
        accepted=accepted,
        baseline=baseline,
        current=current,
        scores={accepted[1]: 0.99},
        targets=[accepted[1]],
        policy=Policy(
            x_tolerance=5,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
        include_details=True,
    )

    assert result["accepted_collision_count"] == 1
    assert result["all_targets_recovered"] is False
    assert result["accepted_collisions"][0]["candidate_reference_index"] == 1
    assert result["accepted_collisions"][0]["kept_reference_index"] == 0


def test_full_reference_safety_rejects_policy_that_merges_accepted_pair() -> None:
    features = {
        "available": True,
        "page_count": 68,
        "pairs": [
            {
                "path": "accepted/page.json",
                "first_index": 0,
                "first_bbox": [10, 20, 14, 120],
                "second_index": 1,
                "second_bbox": [15, 20, 19, 120],
                "x_distance": 5.0,
                "vertical_overlap_ratio": 1.0,
                "height_ratio": 1.0,
            }
        ],
    }

    unsafe = _accepted_root_collisions(
        features,
        Policy(
            x_tolerance=5,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
    )
    safe = _accepted_root_collisions(
        features,
        Policy(
            x_tolerance=4,
            min_vertical_overlap_ratio=0.9,
            min_height_ratio=0.9,
        ),
    )

    assert unsafe["collision_count"] == 1
    assert safe["collision_count"] == 0


def test_build_report_runs_policy_sweep_with_separate_baseline_metrics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    accepted_path = tmp_path / "accepted.json"
    baseline_final = tmp_path / "baseline_final.json"
    current_final = tmp_path / "current_final.json"
    current_scored = tmp_path / "current_scored.json"
    current_batch = tmp_path / "current_batch.json"
    baseline_batch = tmp_path / "baseline_batch.json"
    targets_path = tmp_path / "targets.json"

    accepted = [[10, 20, 14, 120], [100, 20, 104, 120]]
    baseline = [accepted[0]]
    current = accepted

    accepted_path.write_text(json.dumps(accepted), encoding="utf-8")
    baseline_final.write_text(json.dumps(baseline), encoding="utf-8")
    current_final.write_text(json.dumps(current), encoding="utf-8")
    current_scored.write_text(
        json.dumps([{"bbox": accepted[1], "score": 0.99}]),
        encoding="utf-8",
    )
    current_batch.write_text(
        json.dumps(
            {
                "status": "completed",
                "expected_commit": "current",
                "runs": [
                    {
                        "label": "focus",
                        "contract": {
                            "artifacts": {
                                "final_barlines": {
                                    "exists": True,
                                    "path": str(current_final),
                                },
                                "cnn_scored": {
                                    "exists": True,
                                    "path": str(current_scored),
                                },
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    baseline_batch.write_text(
        json.dumps(
            {
                "status": "completed",
                "expected_commit": "baseline",
                "runs": [
                    {
                        "label": "focus",
                        "contract": {
                            "artifacts": {
                                "final_barlines": {
                                    "exists": True,
                                    "path": str(baseline_final),
                                }
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    targets_path.write_text(
        json.dumps(
            {
                "pages": {
                    "focus": {
                        "score": "synthetic",
                        "page": "page_001",
                        "accepted_barlines": str(accepted_path),
                        "targets": [{"accepted_bbox": accepted[1]}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        multiplicity,
        "load_json_boxes",
        lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
    )

    report = multiplicity.build_report(
        current_batch=current_batch,
        baseline_batch=baseline_batch,
        targets_path=targets_path,
        accepted_root=None,
    )

    assert report["status"] == "completed"
    assert report["pages"]["focus"]["baseline_metrics"] == {
        "tp": 1,
        "fp": 0,
        "fn": 1,
    }
    assert report["policy_sweep"]["policy_count"] == 81
