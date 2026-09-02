from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issue294_model_lineage_records_weight_generation_confounds() -> None:
    payload = json.loads(
        (PROJECT_ROOT / "tools/issue294/model_lineage.json").read_text(encoding="utf-8")
    )

    variants = payload["variants"]
    assert variants["A_pinned_historical"]["segnet"].startswith("segnet_155-")
    assert "pytorch_model_220-" in variants["A_pinned_historical"]["transformer"]
    assert variants["B_maintained_family_candidate"]["segnet"].startswith("segnet_308-")
    assert "pytorch_model_331-" in variants["B_maintained_family_candidate"]["transformer"]
    assert variants["C_upstream_main_observed_2026_09_03"]["segnet"].startswith("segnet_308-")
    assert "pytorch_model_426-" in variants["C_upstream_main_observed_2026_09_03"]["transformer"]
    assert payload["interpretation"]["A_vs_B_is_runtime_only"] is False
    assert payload["interpretation"]["B_is_current_upstream_main"] is False
