import json
from pathlib import Path

from tools.issue255.run_gate05_first_loss_trace import ROOT, _resolve_record_path


def test_resolve_record_path_maps_workspace_to_repository() -> None:
    assert _resolve_record_path("/workspace/logs/result.json") == ROOT / "logs/result.json"


def test_gate05_target_manifest_is_analysis_only() -> None:
    path = ROOT / "tools/issue255/gate05_targets.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["accepted_reference_runtime_input"] is False
    assert set(payload["pages"]) == {"prokofiev", "shostakovich"}
    assert sum(len(page["targets"]) for page in payload["pages"].values()) == 8
    for page in payload["pages"].values():
        assert Path(page["accepted_barlines"]).name == "pipeline2_no_peak_filtered_cnn.json"
        for target in page["targets"]:
            assert len(target["accepted_bbox"]) == 4
