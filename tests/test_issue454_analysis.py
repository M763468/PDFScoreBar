import json

import pytest

from tools.issue447.deepening_analyze import numbering_payload


def test_single_page_uses_complete_per_page_payload(tmp_path):
    page = tmp_path / "outputs/page_013"
    page.mkdir(parents=True)
    payload = {
        "pages": [{"systems": [{"measures": [1, 2]}]}],
        "numbering_metadata": {"next_number": 3},
    }
    (page / "numbering_final.json").write_text(json.dumps(payload))
    assert numbering_payload(tmp_path, ["page_013"], "outputs", "numbering_final.json") == payload


def test_missing_multi_page_combined_or_single_page_payload_is_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        numbering_payload(tmp_path, ["a", "b"], "outputs", "numbering_final.json")
    with pytest.raises(FileNotFoundError):
        numbering_payload(tmp_path, ["a"], "outputs", "numbering_final.json")
