from tools.eval2_measure_count_kpi import variant_boxes


def test_variant_boxes_filters_by_score_and_unit_height() -> None:
    scored = [
        {"bbox": [10, 0, 14, 100], "score": 0.9},
        {"bbox": [20, 0, 24, 50], "score": 0.9},
        {"bbox": [30, 0, 34, 100], "score": 0.4},
    ]

    boxes = variant_boxes("score_ge_0p5_minh_2p8", [], scored)

    assert boxes == [(10, 0, 14, 100)]


def test_variant_boxes_applies_center_nms_after_filters() -> None:
    scored = [
        {"bbox": [10, 0, 14, 100], "score": 0.8},
        {"bbox": [15, 0, 19, 100], "score": 0.9},
        {"bbox": [80, 0, 84, 100], "score": 0.7},
    ]

    boxes = variant_boxes("score_ge_0p5_xnms_0p3", [], scored)

    assert boxes == [(15, 0, 19, 100), (80, 0, 84, 100)]


def test_variant_boxes_applies_soft_short_low_confidence_filter() -> None:
    scored = [
        {"bbox": [10, 0, 14, 100], "score": 0.9},
        {"bbox": [20, 0, 24, 100], "score": 0.95},
        {"bbox": [30, 0, 34, 100], "score": 0.99},
        {"bbox": [40, 0, 44, 72], "score": 0.7},
        {"bbox": [50, 0, 54, 72], "score": 0.99},
    ]

    boxes = variant_boxes("score_ge_0p5_minh_2p8_softshort_2p9_scorelt_0p9", [], scored)

    assert boxes == [
        (10, 0, 14, 100),
        (20, 0, 24, 100),
        (30, 0, 34, 100),
        (50, 0, 54, 72),
    ]
