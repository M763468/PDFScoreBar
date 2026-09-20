from src.pipeline.review.apply_corrections import (
    _barline_neighborhood_keys,
    _remap_measure_key,
    _reuse_auto_mmr_overrides,
)


def _numbering(*measure_bboxes):
    return {
        "pages": [
            {
                "page_number": 1,
                "width": 400,
                "height": 100,
                "systems": [
                    {
                        "staves": [{"bbox": [0, 0, 400, 100]}],
                        "measures": [
                            {"number": index + 1, "bbox": list(bbox)}
                            for index, bbox in enumerate(measure_bboxes)
                        ],
                    }
                ],
            }
        ]
    }


def test_barline_neighborhood_only_targets_measures_touching_changed_barline():
    source = _numbering(
        [0, 0, 100, 100],
        [100, 0, 200, 100],
        [200, 0, 300, 100],
        [300, 0, 400, 100],
    )
    corrected = _numbering(
        [0, 0, 100, 100],
        [100, 0, 300, 100],
        [300, 0, 400, 100],
    )
    correction = [{"page": 0, "op": "remove", "bbox": [198, 0, 202, 100]}]

    assert _barline_neighborhood_keys(source, correction, page_index=0) == {
        (0, 0, 1),
        (0, 0, 2),
    }
    assert _barline_neighborhood_keys(corrected, correction, page_index=0) == {
        (0, 0, 1)
    }


def test_measure_key_remaps_by_geometry_after_removed_barline():
    source = _numbering(
        [0, 0, 100, 100],
        [100, 0, 200, 100],
        [200, 0, 300, 100],
        [300, 0, 400, 100],
    )
    corrected = _numbering(
        [0, 0, 100, 100],
        [100, 0, 300, 100],
        [300, 0, 400, 100],
    )

    assert _remap_measure_key(source, corrected, (0, 0, 3), strict=True) == (0, 0, 2)


def test_reuse_auto_mmr_keeps_untouched_results_and_drops_changed_neighborhood():
    source = _numbering(
        [0, 0, 100, 100],
        [100, 0, 200, 100],
        [200, 0, 300, 100],
        [300, 0, 400, 100],
    )
    corrected = _numbering(
        [0, 0, 100, 100],
        [100, 0, 300, 100],
        [300, 0, 400, 100],
    )
    source_mmr = {
        "measure_overrides": [
            {"page": 0, "system": 0, "measure": 0, "skip": 2},
            {"page": 0, "system": 0, "measure": 1, "skip": 3},
            {"page": 0, "system": 0, "measure": 3, "skip": 4},
        ]
    }

    reused = _reuse_auto_mmr_overrides(
        source_mmr,
        page_index=0,
        source_base=source,
        corrected_base=corrected,
        barline_changed=True,
        affected_source_keys={(0, 0, 1), (0, 0, 2)},
        affected_corrected_keys={(0, 0, 1)},
        manual_corrected_keys=set(),
    )

    assert reused == [
        {"page": 0, "system": 0, "measure": 0, "skip": 2},
        {"page": 0, "system": 0, "measure": 2, "skip": 4},
    ]


def test_manual_mmr_key_prevents_reuse_at_same_corrected_measure():
    source = _numbering(
        [0, 0, 100, 100],
        [100, 0, 200, 100],
        [200, 0, 300, 100],
    )
    corrected = _numbering(
        [0, 0, 100, 100],
        [100, 0, 300, 100],
    )
    source_mmr = {
        "measure_overrides": [
            {"page": 0, "system": 0, "measure": 0, "skip": 2},
        ]
    }

    reused = _reuse_auto_mmr_overrides(
        source_mmr,
        page_index=0,
        source_base=source,
        corrected_base=corrected,
        barline_changed=True,
        affected_source_keys=set(),
        affected_corrected_keys=set(),
        manual_corrected_keys={(0, 0, 0)},
    )

    assert reused == []
