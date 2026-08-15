from tools.issue274.audit_positive_geometry_disagreements import slice_one_measure


def _payload() -> tuple[dict, dict]:
    systems = [
        {
            "staves": [{"bbox": [0, 10, 100, 20]}],
            "measures": [{"bbox": [0, 10, 20, 20]}, {"bbox": [20, 10, 40, 20]}],
        },
        {
            "staves": [{"bbox": [0, 30, 100, 40]}],
            "measures": [{"bbox": [0, 30, 20, 40]}, {"bbox": [20, 30, 40, 40]}],
        },
    ]
    page_data = {"pages": [{"page_number": 7, "systems": systems}]}
    support = {
        "views": {
            view: {"pages": [{"systems": systems}]}
            for view in ("primary", "fallback", "implicit_start_alternate")
        }
    }
    return page_data, support


def test_slice_one_measure_preserves_selected_geometry_and_staff() -> None:
    page_data, support = _payload()
    sliced_page, sliced_support = slice_one_measure(page_data, support, 1, 1)

    assert sliced_page["pages"][0]["systems"][0]["staves"] == [{"bbox": [0, 30, 100, 40]}]
    assert sliced_page["pages"][0]["systems"][0]["measures"] == [{"bbox": [20, 30, 40, 40]}]
    for view in sliced_support["views"].values():
        assert view["pages"][0]["systems"][0]["staves"] == [{"bbox": [0, 30, 100, 40]}]
        assert view["pages"][0]["systems"][0]["measures"] == [{"bbox": [20, 30, 40, 40]}]


def test_slice_one_measure_does_not_mutate_inputs() -> None:
    page_data, support = _payload()
    slice_one_measure(page_data, support, 1, 1)

    assert len(page_data["pages"][0]["systems"]) == 2
    assert len(support["views"]["primary"]["pages"][0]["systems"][1]["measures"]) == 2
