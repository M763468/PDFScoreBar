import numpy as np
import pytest

pytest.importorskip("cv2")

from src.pipeline.steps.candidate_filters import filter_probe_candidates
from src.pipeline.steps.low_paper_candidate_rescue import rescue_low_paper_candidates


def test_filter_rescues_dark_vertical_inside_large_existing_gap() -> None:
    image = np.full((300, 400, 3), 255, dtype=np.uint8)
    candidate = (178, 100, 182, 200)
    image[100:200, 178:182] = 0
    existing = [
        (18, 100, 22, 200),
        (78, 100, 82, 200),
        (298, 100, 302, 200),
    ]

    kept_without_rescue, dropped_without_rescue = filter_probe_candidates(
        candidates=[candidate],
        image=image,
        existing_boxes=existing,
        left_margin_ratio=0.0,
        min_paper_overlap_ratio=0.6,
    )
    kept_with_rescue, dropped_with_rescue = filter_probe_candidates(
        candidates=[candidate],
        image=image,
        existing_boxes=existing,
        left_margin_ratio=0.0,
        min_paper_overlap_ratio=0.6,
        rescue_low_paper_verticals=True,
    )

    assert kept_without_rescue == []
    assert dropped_without_rescue[0]["reasons"] == ["low_paper_overlap"]
    assert kept_with_rescue == [candidate]
    assert dropped_with_rescue == []


def test_rescue_requires_only_low_paper_rejection() -> None:
    candidate = (100, 100, 104, 200)
    rescued, remaining, details = rescue_low_paper_candidates(
        dropped=[
            {
                "bbox": candidate,
                "reasons": ["low_paper_overlap", "left_margin_zone"],
                "ink_ratio": 1.0,
            }
        ],
        existing_boxes=[(20, 100, 24, 200), (220, 100, 224, 200)],
        median_height=100.0,
    )

    assert rescued == []
    assert len(remaining) == 1
    assert details == []


def test_rescue_uses_cross_band_alignment() -> None:
    upper = (100, 100, 104, 200)
    lower = (102, 300, 106, 400)
    rescued, remaining, details = rescue_low_paper_candidates(
        dropped=[
            {"bbox": upper, "reasons": ["low_paper_overlap"], "ink_ratio": 1.0},
            {"bbox": lower, "reasons": ["low_paper_overlap"], "ink_ratio": 1.0},
        ],
        existing_boxes=[],
        median_height=100.0,
    )

    assert rescued == [upper, lower]
    assert remaining == []
    assert all("aligned_candidate" in detail["supports"] for detail in details)


def test_rescue_does_not_duplicate_narrow_same_band_seed() -> None:
    upper = (100, 100, 104, 200)
    lower = (102, 300, 106, 400)
    rescued, remaining, details = rescue_low_paper_candidates(
        dropped=[
            {"bbox": upper, "reasons": ["low_paper_overlap"], "ink_ratio": 1.0},
            {"bbox": lower, "reasons": ["low_paper_overlap"], "ink_ratio": 1.0},
        ],
        existing_boxes=[(99, 100, 105, 200)],
        median_height=100.0,
    )

    assert rescued == [lower]
    assert any(tuple(item["bbox"]) == upper for item in remaining)
    assert details[0]["supports"] == ["aligned_existing"]


def test_rescue_refines_wide_existing_seed() -> None:
    candidate = (100, 100, 104, 200)
    rescued, remaining, details = rescue_low_paper_candidates(
        dropped=[{"bbox": candidate, "reasons": ["low_paper_overlap"], "ink_ratio": 1.0}],
        existing_boxes=[(92, 100, 116, 200)],
        median_height=100.0,
    )

    assert rescued == [candidate]
    assert remaining == []
    assert details[0]["supports"] == ["wide_seed_refinement"]


def test_gate05_target_geometries_are_supported_without_page_rules() -> None:
    prokofiev = (3565, 1930, 3569, 2132)
    shostakovich_upper = (2948, 5218, 2952, 5410)
    shostakovich_lower = (2950, 5910, 2954, 6134)
    dropped = [
        {"bbox": prokofiev, "reasons": ["low_paper_overlap"], "ink_ratio": 0.94},
        {
            "bbox": shostakovich_upper,
            "reasons": ["low_paper_overlap"],
            "ink_ratio": 1.0,
        },
        {
            "bbox": shostakovich_lower,
            "reasons": ["low_paper_overlap"],
            "ink_ratio": 1.0,
        },
    ]
    existing = [
        (2869, 1930, 2873, 2132),
        (6381, 1930, 6385, 2132),
        (190, 2400, 194, 2602),
        (666, 2400, 670, 2602),
    ]

    rescued, remaining, details = rescue_low_paper_candidates(
        dropped=dropped,
        existing_boxes=existing,
        median_height=202.0,
    )

    assert set(rescued) == {prokofiev, shostakovich_upper, shostakovich_lower}
    assert remaining == []
    support_by_box = {tuple(detail["bbox"]): detail["supports"] for detail in details}
    assert "large_gap" in support_by_box[prokofiev]
    assert "aligned_candidate" in support_by_box[shostakovich_upper]
    assert "aligned_candidate" in support_by_box[shostakovich_lower]
