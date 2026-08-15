from tools.issue274.run_original_geometry_graft import compare_geometry, geometry_snapshot


def _payload(*, measure_bbox=(10, 20, 30, 40), staff_bbox=(9, 20, 40, 40)):
    return {
        "pages": [
            {
                "systems": [
                    {
                        "staves": [{"bbox": list(staff_bbox)}],
                        "measures": [{"bbox": list(measure_bbox)}],
                    }
                ]
            }
        ]
    }


def test_geometry_snapshot_captures_only_mmr_geometry():
    snapshot = geometry_snapshot(_payload())

    assert snapshot == {
        "system_count": 1,
        "staff_counts": [1],
        "measure_counts": [1],
        "staff_bboxes": [[[9, 20, 40, 40]]],
        "measure_bboxes": [[[10, 20, 30, 40]]],
    }


def test_compare_geometry_requires_exact_topology_and_bboxes():
    o0 = _payload()
    changed = _payload(staff_bbox=(9, 21, 40, 41))

    comparison = compare_geometry(o0, changed)

    assert comparison["topology_equal"] is True
    assert comparison["staff_bbox_exact"] is False
    assert comparison["measure_bbox_exact"] is True
    assert comparison["geometry_exact"] is False


def test_compare_geometry_detects_topology_change():
    o0 = _payload()
    changed = _payload()
    changed["pages"][0]["systems"].append({"staves": [], "measures": []})

    comparison = compare_geometry(o0, changed)

    assert comparison["topology_equal"] is False
    assert comparison["geometry_exact"] is False
