from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.pipeline.mmr_geometry_handoff import build_mmr_page_context
from src.pipeline.mmr_geometry_layout import (
    numbering_layout_signature,
    require_compatible_mmr_layout,
)
from src.pipeline.mmr_staff_support import (
    PROJECT_ROOT,
    _validated_masks,
    _worker_visible_path,
    prepare_mmr_staff_masks,
)


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


def test_skip_existing_hydrates_mmr_staff_geometry_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "page_001.png"
    image.write_bytes(b"image")
    page_intermediate = tmp_path / "run" / "intermediate" / "page_001"
    page_intermediate.mkdir(parents=True)
    numbering_base = page_intermediate / "numbering_base.json"
    numbering_base.write_text("{}\n", encoding="utf-8")
    (page_intermediate / "overrides_mmr.json").write_text("{}\n", encoding="utf-8")

    orchestrator_intermediate = tmp_path / "run" / "intermediate"
    result_root = orchestrator_intermediate / "mmr_staff_geometry" / "page_001"
    result_root.mkdir(parents=True)
    staff_mask = result_root / "homr" / "batch" / "page_001" / "page_001_staff_mask.png"
    staff_mask.parent.mkdir(parents=True)
    staff_mask.write_bytes(b"staff")
    result_path = result_root / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "producer": "HybridDetector._run_homr_in_process",
                "producer_runtime": "current_pipeline_homr",
                "historical_detector_artifact_runtime_input": False,
                "staff_masks": {str(image.resolve()): str(staff_mask)},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.pipeline.mmr_staff_support.get_pipeline_python",
        lambda _step: ["python"],
    )
    monkeypatch.setattr(
        "src.pipeline.mmr_staff_support.run_with_logging",
        lambda *_args, **_kwargs: pytest.fail("worker should not run for valid retained result"),
    )

    page_ctx = {
        "page_001": {
            "image_path": image,
            "numbering_base": numbering_base,
            "intermediate_dir": page_intermediate,
            "resolved": {},
        }
    }
    orchestrator = SimpleNamespace(
        intermediate_dir=orchestrator_intermediate,
        config={},
        skip_existing=True,
    )

    masks = prepare_mmr_staff_masks(orchestrator, ["page_001"], set(), page_ctx)

    assert masks == {}
    assert page_ctx["page_001"]["mmr_staff_mask"] == staff_mask
    assert page_ctx["page_001"]["resolved"]["mmr_staff_geometry"] == {
        "staff_mask": str(staff_mask),
        "producer": "HybridDetector._run_homr_in_process",
        "producer_runtime": "current_pipeline_homr",
        "historical_detector_artifact_runtime_input": False,
        "result_path": str(result_path),
    }


def test_worker_visible_path_translates_repository_path_for_docker() -> None:
    repository_path = PROJECT_ROOT / "data" / "evaluation2" / "page_001.png"

    assert _worker_visible_path(repository_path, docker_exec=True) == (
        "/workspace/data/evaluation2/page_001.png"
    )
