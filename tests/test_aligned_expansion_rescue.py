from src.pipeline.steps.candidate_filters import select_aligned_expansion_rescues


def _select(dropped, existing=((100, 200, 110, 300),)):
    return select_aligned_expansion_rescues(
        dropped,
        existing,
        x_tolerance=4.0,
        min_existing_vertical_coverage=0.8,
        min_height_ratio=1.25,
        max_height_ratio=2.0,
    )


def test_selects_sole_low_paper_overlap_only() -> None:
    selected = _select(
        [
            {"bbox": [103, 175, 107, 325], "reasons": ["low_paper_overlap"]},
            {
                "bbox": [103, 175, 107, 325],
                "reasons": ["low_paper_overlap", "left_margin_zone"],
            },
        ]
    )

    assert selected == [(103, 175, 107, 325)]


def test_rejects_bad_alignment_coverage_and_height_ratio() -> None:
    selected = _select(
        [
            {"bbox": [120, 175, 124, 325], "reasons": ["low_paper_overlap"]},
            {"bbox": [103, 221, 107, 350], "reasons": ["low_paper_overlap"]},
            {"bbox": [103, 190, 107, 310], "reasons": ["low_paper_overlap"]},
            {"bbox": [103, 100, 107, 350], "reasons": ["low_paper_overlap"]},
        ]
    )

    assert selected == []


def test_selects_one_deterministic_best_candidate_per_existing_box() -> None:
    selected = _select(
        [
            {"bbox": [103, 175, 107, 325], "reasons": ["low_paper_overlap"]},
            {"bbox": [102, 175, 106, 325], "reasons": ["low_paper_overlap"]},
        ]
    )

    assert selected == [(103, 175, 107, 325)]


def test_left_margin_drop_is_not_rescued() -> None:
    assert (
        _select(
            [
                {
                    "bbox": [103, 175, 107, 325],
                    "reasons": ["left_margin_zone", "low_paper_overlap"],
                }
            ]
        )
        == []
    )
