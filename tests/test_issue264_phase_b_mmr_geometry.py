from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.mmr_geometry_handoff import build_mmr_page_context
from src.pipeline.mmr_geometry_layout import (
    numbering_layout_signature,
    require_compatible_mmr_layout,
)
from src.pipeline.mmr_staff_support import _validated_masks


def _payload(counts: list[int]) -> dict:
    return {
        "pages": [
            {
                "page_number": 1,
                "width": 100,
                "height": 200,
                "systems": [
                    {
                        "staves": [],
                        "measures": [
                            {"number": index + 1, "bbox": [index, 0, index + 1, 10]}
                            for index in range(count)
                        ],
                    }
                    for count in counts
                ],
            }
        ]
    }


def test_layout_signature_ignores_geometry_but_preserves_measure_indices() -> None:
    base = _payload([5, 7, 3])
    mmr = _payload([5, 7, 3])
    mmr["pages"][0]["systems"][1]["measures"][0]["bbox"] = [40, 50, 60, 70]

    assert numbering_layout_signature(base) == ((5, 7, 3),)
    require_compatible_mmr_layout(base, mmr, page_id="page_001")


def test_layout_guard_rejects_mmr_index_drift() -> None:
    with pytest.raises(RuntimeError, match="changed the numbering index layout"):
        require_compatible_mmr_layout(
            _payload([5, 7, 3]),
            _payload([5, 6, 4]),
            page_id="page_001",
        )


def test_mmr_handoff_does_not_replace_phase_a_numbering_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_path = tmp_path / "numbering_base.json"
    mmr_path = tmp_path / "numbering_mmr_geometry.json"
    staff_mask = tmp_path / "fresh_staff_mask.png"
    base_path.write_text("{}\n", encoding="utf-8")
    mmr_path.write_text("{}\n", encoding="utf-8")
    staff_mask.write_bytes(b"staff")

    page_ctx = {
        "page_001": {
            "numbering_base": base_path,
            "resolved": {"staff_mask": "proxy_staff.png"},
        }
    }

    monkeypatch.setattr(
        "src.pipeline.mmr_geometry_handoff.prepare_mmr_staff_masks",
        lambda *_args, **_kwargs: {"page_001": staff_mask},
    )
    monkeypatch.setattr(
        "src.pipeline.mmr_geometry_handoff.build_mmr_numbering_path",
        lambda *_args, **_kwargs: mmr_path,
    )

    mmr_ctx = build_mmr_page_context(object(), ["page_001"], set(), page_ctx)

    assert page_ctx["page_001"]["numbering_base"] == base_path
    assert page_ctx["page_001"]["resolved"]["staff_mask"] == "proxy_staff.png"
    assert mmr_ctx["page_001"]["numbering_base"] == mmr_path


def test_staff_geometry_result_requires_current_producer_and_runtime(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    accepted = {
        "status": "completed",
        "producer": "HybridDetector._run_homr_in_process",
        "producer_runtime": "current_pipeline_homr",
        "historical_detector_artifact_runtime_input": False,
        "staff_masks": {"page.png": "fresh_staff.png"},
    }

    assert _validated_masks(accepted, result_path) == accepted["staff_masks"]

    wrong_producer = dict(accepted)
    wrong_producer["producer"] = "pinned_stage_e_evaluator"
    with pytest.raises(ValueError, match="Unexpected MMR staff-geometry producer"):
        _validated_masks(wrong_producer, result_path)

    wrong_runtime = dict(accepted)
    wrong_runtime["producer_runtime"] = "stage_e_verified"
    with pytest.raises(ValueError, match="Unexpected MMR staff-geometry runtime"):
        _validated_masks(wrong_runtime, result_path)

    historical = dict(accepted)
    historical["historical_detector_artifact_runtime_input"] = True
    with pytest.raises(ValueError, match="must not use historical detector artifacts"):
        _validated_masks(historical, result_path)
