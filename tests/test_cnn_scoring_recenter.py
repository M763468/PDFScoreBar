import numpy as np

from src.pipeline.steps.cnn_scoring import (
    _compute_bbox_ink_center_x,
    _suppress_short_candidates_by_unit_height,
    apply_nms,
)


def test_bbox_ink_recenter_honors_min_width_unit_ratio():
    img = np.full((40, 30, 3), 255, dtype=np.uint8)
    img[:, 10] = 0

    narrow_box = [10, 0, 13, 40]
    assert (
        _compute_bbox_ink_center_x(
            img,
            narrow_box,
            apply_if_width_ge_unit_ratio=0.4,
        )
        is None
    )

    eligible_box = [10, 0, 14, 40]
    assert (
        _compute_bbox_ink_center_x(
            img,
            eligible_box,
            apply_if_width_ge_unit_ratio=0.4,
        )
        == 10
    )


def test_apply_nms_can_disable_x_distance_suppression():
    scored = [
        {"bbox": [100, 10, 104, 110], "score": 0.99},
        {"bbox": [109, 10, 113, 110], "score": 0.98},
    ]

    apply_nms(scored, x_dist_unit_ratio=0.0)

    assert [item["score"] for item in scored] == [0.99, 0.98]


def test_apply_nms_default_suppresses_nearby_vertical_boxes():
    scored = [
        {"bbox": [100, 10, 104, 110], "score": 0.99},
        {"bbox": [109, 10, 113, 110], "score": 0.98},
    ]

    apply_nms(scored)

    assert scored[1]["score"] == 0.0


def test_suppress_short_candidates_by_unit_height_uses_page_scale():
    scored = [
        {"bbox": [10, 0, 14, 100], "score": 0.99},
        {"bbox": [20, 0, 24, 102], "score": 0.95},
        {"bbox": [30, 0, 34, 62], "score": 0.8},
    ]

    _suppress_short_candidates_by_unit_height(scored, min_height_unit_ratio=2.5)

    assert scored[0]["score"] == 0.99
    assert scored[1]["score"] == 0.95
    assert scored[2]["score"] == 0.0
