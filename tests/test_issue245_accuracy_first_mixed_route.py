import json
from pathlib import Path

from tools.issue245 import prepare_accuracy_first_mixed_route as probe


def write_boxes(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([[index, 0, index + 1, 10] for index in range(count)]))


def test_canonical_keys_uses_established_full68_set() -> None:
    keys = probe.canonical_keys()

    assert len(keys) == probe.EXPECTED_PAGES
    assert len(set(keys)) == probe.EXPECTED_PAGES
    assert ("Va_Prokofiev_Symphony1", "page_001") in keys
    assert ("Va__Prokofiev_Symphony5", "page_015") in keys


def test_layer_paths_supports_current_batch_layout(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    page = "page_001"
    hybrid = run_root / "hybrid_results" / f"{page}_hybrid.json"
    baseline = run_root / "baseline" / "batch" / page / f"{page}_detections.json"
    sr = run_root / "sr" / "batch" / page / f"{page}_detections.json"
    omr = run_root / "omr_sr" / page / "predictions.json"
    for path in (hybrid, baseline, sr, omr):
        write_boxes(path, 1)

    result = probe.layer_paths(
        tmp_path,
        {
            "score": "score",
            "page": page,
            "hybrid_predictions": str(hybrid),
        },
    )

    assert result == {
        "baseline": baseline,
        "sr": sr,
        "omr": omr,
        "hybrid": hybrid,
    }


def test_layer_paths_supports_historical_nested_layout(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    page = "page_001"
    hybrid = run_root / "hybrid_results" / f"{page}_hybrid.json"
    baseline = run_root / "baseline" / page / page / f"{page}_detections.json"
    sr = run_root / "sr" / page / page / f"{page}_detections.json"
    omr = run_root / "omr_sr" / page / "predictions.json"
    for path in (hybrid, baseline, sr, omr):
        write_boxes(path, 1)

    result = probe.layer_paths(
        tmp_path,
        {
            "score": "score",
            "page": page,
            "hybrid_predictions": str(hybrid),
        },
    )

    assert result["baseline"] == baseline
    assert result["sr"] == sr
    assert result["omr"] == omr


def test_aggregate_comparisons_reports_differing_pages() -> None:
    equal = {
        "left": {"count": 2},
        "right": {"count": 2},
        "matched_count": 2,
        "left_only": {"count": 0},
        "right_only": {"count": 0},
        "semantic_equal": True,
    }
    different = {
        "left": {"count": 3},
        "right": {"count": 4},
        "matched_count": 2,
        "left_only": {"count": 1},
        "right_only": {"count": 2},
        "semantic_equal": False,
    }

    result = probe.aggregate_comparisons(
        [
            {"score": "score_a", "page": "page_001", "comparison": equal},
            {"score": "score_b", "page": "page_002", "comparison": different},
        ]
    )

    assert result == {
        "pages": 2,
        "pages_semantic_equal": 1,
        "pages_different": 1,
        "historical_count": 5,
        "mixed_count": 6,
        "matched_count": 4,
        "historical_only_count": 1,
        "mixed_only_count": 2,
        "differing_pages": ["score_b/page_002"],
    }
