import numpy as np

from src.pipeline.steps.candidate_filters import filter_probe_candidates, trim_box_to_ink


def test_filter_probe_candidates_basic():
    image = np.zeros((100, 100), dtype=np.uint8)
    image.fill(255)
    candidates = [(20, 10, 25, 50), (5, 10, 10, 50)]
    for x1, y1, x2, y2 in candidates:
        image[y1:y2, x1:x2] = 0
    existing = [(50, 10, 55, 50)]
    keep, dropped = filter_probe_candidates(candidates, image, existing, left_margin_ratio=0.12)
    assert len(keep) == 1
    assert keep[0] == (20, 10, 25, 50)


def test_trim_box_to_ink():
    image = np.zeros((100, 100), dtype=np.uint8)
    image.fill(255)
    # Draw a 20px tall line in a 40px box
    image[40:60, 20:25] = 0
    box = (20, 30, 25, 70)
    trimmed = trim_box_to_ink(image, box, ink_threshold=180, min_ink_ratio=0.1)
    assert trimmed[1] == 40
    assert trimmed[3] == 60


def test_filter_probe_candidates_clef_overlap():
    image = np.full((100, 100), 255, dtype=np.uint8)
    clef_mask = np.zeros((100, 100), dtype=np.uint8)
    # 1. Candidate in clef zone with overlap
    candidates = [(40, 10, 45, 50)]
    clef_mask[10:50, 40:45] = 255
    keep, dropped = filter_probe_candidates(
        candidates, image, [], clef_mask=clef_mask, clef_left_ratio=0.5
    )
    assert len(keep) == 0
    assert "clef_mask_overlap" in dropped[0]["reasons"]


def test_filter_probe_candidates_staff_overlap():
    image = np.full((100, 100), 255, dtype=np.uint8)
    staff_mask = np.zeros((100, 100), dtype=np.uint8)
    # 1. Candidate with NO staff overlap
    candidates = [(50, 10, 55, 50)]
    keep, dropped = filter_probe_candidates(
        candidates, image, [], staff_mask=staff_mask, min_staff_overlap_ratio=0.1
    )
    assert len(keep) == 0
    assert "no_staff_overlap" in dropped[0]["reasons"]


def test_filter_probe_candidates_too_short():
    image = np.full((100, 100), 255, dtype=np.uint8)
    existing = [(20, 10, 25, 60)]  # h=50
    candidates = [(30, 20, 35, 40)]  # h=20
    # min_h = 50 * 0.6 = 30. Candidate is 20 < 30.
    keep, dropped = filter_probe_candidates(
        candidates, image, existing, min_height_median_ratio=0.6, left_margin_ratio=0.0
    )
    assert len(keep) == 0
    assert "too_short_vs_existing_median" in dropped[0]["reasons"]


def test_split_box_vertically():
    from src.pipeline.steps.candidate_filters import split_box_vertically

    image = np.full((200, 100), 255, dtype=np.uint8)
    # Draw two lines with a gap
    image[20:50, 40:45] = 0  # h=30
    image[120:150, 40:45] = 0  # h=30
    box = (40, 10, 45, 160)
    # min_gap=50, min_segment_h=20
    splits = split_box_vertically(image, box, min_gap=50, min_segment_h=20)
    assert len(splits) == 2
    # Verify approximate y ranges (trimming might happen)
    assert abs(splits[0][1] - 20) <= 1
    assert abs(splits[0][3] - 50) <= 1
    assert abs(splits[1][1] - 120) <= 1
    assert abs(splits[1][3] - 150) <= 1
