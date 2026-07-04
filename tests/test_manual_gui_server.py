from types import SimpleNamespace

from tools.gt_relabel_gui.server import _manual_output_for, _page_config_for


def test_manual_output_for_uses_page_local_manual_outputs_by_page_index():
    server = SimpleNamespace(
        gt_config=[
            {
                "name": "page_001",
                "page": 0,
                "manual_outputs": {
                    "mmr_measure_span": "pages/page_001/corrections/mmr.json",
                },
            },
            {
                "name": "page_003",
                "page": 2,
                "manual_outputs": {
                    "mmr_measure_span": "corrections/mmr_measure_spans.json",
                    "barline_construction": "corrections/barline_construction_overrides.json",
                },
            },
        ]
    )

    assert _page_config_for(server, 2)["name"] == "page_003"
    assert _manual_output_for(server, "mmr_measure_span", 2) == "corrections/mmr_measure_spans.json"
    assert (
        _manual_output_for(server, "barline_construction", "2")
        == "corrections/barline_construction_overrides.json"
    )


def test_manual_output_for_matches_page_name_and_rejects_missing_outputs():
    server = SimpleNamespace(
        gt_config=[
            {"name": "page_003", "page_index": 2},
            {
                "name": "page_004",
                "page_index": 3,
                "manual_outputs": {
                    "measure_construction": "corrections/measure_construction_overrides.json",
                },
            },
        ]
    )

    assert _page_config_for(server, "page_004")["page_index"] == 3
    assert (
        _manual_output_for(server, "measure_construction", "page_004")
        == "corrections/measure_construction_overrides.json"
    )
    assert _manual_output_for(server, "measure_construction", "page_003") is None
    assert _manual_output_for(server, "mmr_measure_span", "page_004") is None
    assert _manual_output_for(server, "mmr_measure_span", "missing") is None
