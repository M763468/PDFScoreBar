from tools.issue245.run_aligned_expansion_candidate_probe import (
    _aligned_expansion_metrics,
    _classify_target,
    _select_aligned_expansions,
)


def test_aligned_expansion_accepts_target_shape() -> None:
    candidate = (1679, 1143, 1683, 1296)
    existing = (1678, 1178, 1688, 1270)

    metrics = _aligned_expansion_metrics(candidate, existing)

    assert metrics is not None
    assert metrics["x_distance"] <= 4.0
    assert metrics["existing_vertical_coverage"] >= 0.8
    assert 1.25 <= metrics["height_ratio"] <= 2.0


def test_aligned_expansion_rejects_unrelated_boxes() -> None:
    existing = (100, 200, 110, 300)

    assert _aligned_expansion_metrics((120, 175, 124, 325), existing) is None
    assert _aligned_expansion_metrics((102, 260, 106, 410), existing) is None
    assert _aligned_expansion_metrics((102, 221, 106, 350), existing) is None


def test_select_aligned_expansions_requires_sole_paper_drop_and_deduplicates() -> None:
    existing = (100, 200, 110, 300)
    dropped = [
        {"bbox": [103, 175, 107, 325], "reasons": ["low_paper_overlap"]},
        {"bbox": [102, 175, 106, 325], "reasons": ["low_paper_overlap"]},
        {
            "bbox": [103, 175, 107, 325],
            "reasons": ["left_margin_zone", "low_paper_overlap"],
        },
    ]

    selected = _select_aligned_expansions(dropped, [existing])

    assert len(selected) == 1
    assert selected[0]["existing_bbox"] == existing
    assert selected[0]["raw_bbox"] == (103, 175, 107, 325)


def test_classify_prefers_existing_then_trimmed_then_raw() -> None:
    rejected = {"accepted": False}
    accepted = {"accepted": True}

    assert (
        _classify_target(
            {
                "current_final": accepted,
                "aligned_trimmed_additive": accepted,
                "aligned_raw_additive": accepted,
            }
        )
        == "already_present_in_current_final"
    )
    assert (
        _classify_target(
            {
                "current_final": rejected,
                "aligned_trimmed_additive": accepted,
                "aligned_raw_additive": accepted,
            }
        )
        == "restored_by_aligned_trimmed_additive"
    )
    assert (
        _classify_target(
            {
                "current_final": rejected,
                "aligned_trimmed_additive": rejected,
                "aligned_raw_additive": accepted,
            }
        )
        == "restored_by_preserving_aligned_raw_expansion"
    )
