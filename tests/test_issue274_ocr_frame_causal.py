from tools.issue274.diagnose_ocr_frame_changed_pages import legacy_frame_dimensions


def test_legacy_frame_dimensions_remove_the_four_20px_border_edges() -> None:
    assert legacy_frame_dimensions(340, 240) == (300, 200)


def test_legacy_frame_dimensions_keep_positive_dimensions() -> None:
    assert legacy_frame_dimensions(20, 39) == (1, 1)
