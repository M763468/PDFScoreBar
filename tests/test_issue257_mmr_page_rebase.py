from copy import deepcopy
from pathlib import Path

import pytest

import src.pipeline.orchestrator as orchestrator_module
import src.pipeline.utils.images as image_utils
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.steps.numbering import (
    load_movement_boundary_payload,
    persisted_final_next_number,
    rebase_mmr_overrides_to_page_local,
)
from src.pipeline.utils.io import load_json, write_json


class _FakeImage:
    shape = (200, 1000, 3)


class _FakeNumberingPipeline:
    def __init__(self) -> None:
        self.numberer = MeasureNumberer()

    def process_page(
        self,
        _barline_boxes,
        _staff_mask,
        _image_size,
        *,
        page_number: int,
        **_kwargs,
    ) -> Page:
        return _one_page(page_number)


class _FakeTwoSystemNumberingPipeline(_FakeNumberingPipeline):
    def process_page(
        self,
        _barline_boxes,
        _staff_mask,
        _image_size,
        *,
        page_number: int,
        **_kwargs,
    ) -> Page:
        page = Page(page_number=page_number, width=1000, height=200)
        for _ in range(2):
            staff = Staff(bbox=BBox(0, 100, 1000, 200))
            for x in [0, 300, 500]:
                staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))
            page.systems.append(System(staves=[staff]))
        return page


def _one_page(page_number: int) -> Page:
    page = Page(page_number=page_number, width=1000, height=200)
    staff = Staff(bbox=BBox(0, 100, 1000, 200))
    for x in [0, 200, 400, 600, 800]:
        staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))
    page.systems.append(System(staves=[staff]))
    return page


def _global_mmr_payload() -> dict:
    return {
        "measure_overrides": [
            {
                "page": page_index,
                "system": 0,
                "measure": 1,
                "skip": page_index + 1,
                "comment": f"MMR global page {page_index}",
                "source": "test:mmr",
            }
            for page_index in range(3)
        ],
        "diagnostics": {"batch": "global"},
    }


def test_rebase_selects_only_current_global_page_without_mutating_source() -> None:
    persisted_payload = _global_mmr_payload()
    original_payload = deepcopy(persisted_payload)

    for page_index in range(3):
        page_local_payload = rebase_mmr_overrides_to_page_local(
            persisted_payload,
            page_index=page_index,
        )

        assert persisted_payload == original_payload
        assert page_local_payload is not persisted_payload
        assert page_local_payload["diagnostics"] == {"batch": "global"}
        assert page_local_payload["measure_overrides"] == [
            {
                "page": 0,
                "system": 0,
                "measure": 1,
                "skip": page_index + 1,
                "comment": f"MMR global page {page_index}",
                "source": "test:mmr",
            }
        ]


def test_three_page_phase_c_preserves_manual_precedence_without_cross_page_leakage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run"
    page_ids = ["page_001", "page_002", "page_003"]
    images = [tmp_path / f"{page_id}.png" for page_id in page_ids]
    persisted_payload = _global_mmr_payload()
    manual_payload = {
        "correction_type": "mmr_measure_span",
        "items": [
            {
                "op": "suppress",
                "page": 1,
                "system": 0,
                "measure": 1,
                "comment": "suppress page 2 automatic MMR override",
            },
            {
                "op": "set_measure_span",
                "page": 2,
                "system": 0,
                "measure": 1,
                "measure_span": 2,
                "comment": "replace page 3 automatic MMR override",
            },
        ],
    }
    manual_overrides_path = tmp_path / "manual_measure_overrides.json"
    write_json(manual_overrides_path, manual_payload)

    resolved = []
    for page_id in page_ids:
        barlines_path = tmp_path / f"{page_id}_barlines.json"
        write_json(barlines_path, [])
        resolved.append(
            {
                "barlines_json": str(barlines_path),
                "staff_mask": str(tmp_path / f"{page_id}_staff_mask.png"),
            }
        )

    config = {
        "inputs": {"measure_overrides": str(manual_overrides_path)},
        "steps": {
            "detection": False,
            "numbering_base": True,
            "mmr_overrides": True,
            "apply_measure_overrides": True,
            "apply_barline_overrides": False,
            "overlay": False,
        },
    }
    orchestrator = PipelineOrchestrator(config, "issue257-test", run_dir)
    orchestrator._persistence = {"numbering_pipeline": _FakeNumberingPipeline()}

    monkeypatch.setattr(
        orchestrator_module,
        "collect_images",
        lambda _config, _run_dir, in_memory_images=None: images,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "resolve_page_ids",
        lambda _config, _images: page_ids,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "resolve_barlines_and_masks_config",
        lambda _config, _page_ids, _page_runs, *, excluded_page_ids: resolved,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "resolve_page_filters",
        lambda _config, _page_ids, _images, _resolved, _excluded_indices: {},
    )
    monkeypatch.setattr(orchestrator_module, "build_manifest", lambda *args, **kwargs: {})
    monkeypatch.setattr(image_utils, "load_image", lambda _path: _FakeImage())

    def fake_phase_a(actual_page_ids, actual_images, actual_resolved, _excluded_page_ids):
        page_ctx = {}
        numbering_base_paths = []
        for index, (page_id, image_path, resolved_item) in enumerate(
            zip(actual_page_ids, actual_images, actual_resolved),
            start=1,
        ):
            page_intermediate = orchestrator.intermediate_dir / page_id
            page_outputs = orchestrator.outputs_dir / page_id
            page_intermediate.mkdir(parents=True, exist_ok=True)
            page_outputs.mkdir(parents=True, exist_ok=True)

            numbering_base = page_intermediate / "numbering_base.json"
            write_json(
                numbering_base,
                {
                    "pages": [
                        {
                            "page_number": index,
                            "width": 1000,
                            "height": 200,
                            "systems": [],
                        }
                    ]
                },
            )
            write_json(page_intermediate / "overrides_mmr.json", persisted_payload)

            page_ctx[page_id] = {
                "index": index,
                "image_path": image_path,
                "resolved": resolved_item,
                "intermediate_dir": page_intermediate,
                "outputs_dir": page_outputs,
                "barlines_path": Path(resolved_item["barlines_json"]),
                "numbering_base": numbering_base,
            }
            numbering_base_paths.append(numbering_base)

        return {
            "page_ctx": page_ctx,
            "numbering_base_paths": numbering_base_paths,
            "barline_override_stats": {},
        }

    monkeypatch.setattr(
        orchestrator,
        "run_base_numbering_and_barline_correction",
        fake_phase_a,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_mmr_batch_detection",
        lambda *_args, **_kwargs: None,
    )

    orchestrator.run()

    assert load_json(manual_overrides_path) == manual_payload
    expected_numbers = [
        [1, 2, 4, 5],
        [6, 7, 8, 9],
        [10, 11, 13, 14],
    ]
    per_page_payloads = []
    for page_index, page_id in enumerate(page_ids):
        overrides_path = run_dir / "intermediate" / page_id / "overrides_mmr.json"
        assert load_json(overrides_path) == persisted_payload

        final_path = run_dir / "outputs" / page_id / "numbering_final.json"
        final_payload = load_json(final_path)
        per_page_payloads.append(final_payload)
        assert final_payload["pages"][0]["page_number"] == page_index + 1
        assert final_payload["numbering_metadata"]["next_number"] == [6, 10, 15][page_index]
        measures = final_payload["pages"][0]["systems"][0]["measures"]
        assert [measure["number"] for measure in measures] == expected_numbers[page_index]

    combined_payload = load_json(run_dir / "outputs" / "numbering_final.json")
    assert combined_payload["pages"] == [payload["pages"][0] for payload in per_page_payloads]
    assert combined_payload["numbering_metadata"]["next_number"] == 15


def test_issue268_explicit_boundary_resets_at_mid_page_system_and_preserves_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run"
    page_ids = ["page_001", "page_002"]
    images = [tmp_path / f"{page_id}.png" for page_id in page_ids]
    resolved = []
    for page_id in page_ids:
        barlines_path = tmp_path / f"{page_id}_barlines.json"
        write_json(barlines_path, [])
        resolved.append(
            {
                "barlines_json": str(barlines_path),
                "staff_mask": str(tmp_path / f"{page_id}_staff_mask.png"),
            }
        )

    config = {
        "inputs": {
            "movement_boundaries": {
                "schema_version": "issue268.movement_boundaries.v1",
                "boundaries": [
                    {
                        "page": 0,
                        "system": 1,
                        "reset_number": 1,
                        "source": "manual",
                        "provenance": {"kind": "fixture", "case": "mid-page"},
                    }
                ],
            }
        },
        "steps": {
            "mmr_overrides": False,
            "apply_measure_overrides": True,
            "overlay": False,
            "apply_barline_overrides": False,
        },
    }
    orchestrator = PipelineOrchestrator(config, "issue268-boundary", run_dir)
    orchestrator._persistence = {"numbering_pipeline": _FakeTwoSystemNumberingPipeline()}

    monkeypatch.setattr(image_utils, "load_image", lambda _path: _FakeImage())

    page_ctx = {}
    for index, (page_id, image_path, resolved_item) in enumerate(
        zip(page_ids, images, resolved), start=1
    ):
        page_intermediate = run_dir / "intermediate" / page_id
        page_outputs = run_dir / "outputs" / page_id
        page_intermediate.mkdir(parents=True)
        page_outputs.mkdir(parents=True)
        page_ctx[page_id] = {
            "index": index,
            "image_path": image_path,
            "resolved": resolved_item,
            "intermediate_dir": page_intermediate,
            "outputs_dir": page_outputs,
            "barlines_path": Path(resolved_item["barlines_json"]),
        }

    final_paths = orchestrator.run_final_numbering_and_overlays(
        page_ids,
        set(),
        page_ctx,
        None,
        load_movement_boundary_payload(config["inputs"]["movement_boundaries"]),
    )

    first_page = load_json(final_paths[0])
    second_page = load_json(final_paths[1])
    assert [
        [measure["number"] for measure in system["measures"]]
        for system in first_page["pages"][0]["systems"]
    ] == [[1, 2], [1, 2]]
    assert [measure["number"] for measure in second_page["pages"][0]["systems"][0]["measures"]] == [
        3,
        4,
    ]
    assert first_page["numbering_metadata"]["movement_boundaries"][0]["provenance"] == {
        "kind": "fixture",
        "case": "mid-page",
    }
    assert first_page["numbering_metadata"]["next_number"] == 3
    assert second_page["numbering_metadata"]["start_number"] == 3


def test_issue268_numberer_boundary_reset_precedes_existing_set_number_override() -> None:
    numberer = MeasureNumberer()
    score = Score()
    page = Page(page_number=1)
    for _ in range(2):
        staff = Staff(bbox=BBox(0, 100, 1000, 200))
        for x in [0, 300, 500]:
            staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))
        page.systems.append(System(staves=[staff]))
    score.pages.append(page)

    next_number = numberer.number_score(
        score,
        start_number=10,
        boundary_resets={(0, 1): 1},
        overrides=[{"page": 0, "system": 1, "measure": 0, "set_number": 7}],
    )

    assert [measure.number for measure in score.pages[0].systems[0].measures] == [10, 11]
    assert [measure.number for measure in score.pages[0].systems[1].measures] == [7, 8]
    assert next_number == 9


def test_issue268_movement_boundary_payload_validation_and_old_skip_artifact_fallback(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="reset_number"):
        load_movement_boundary_payload(
            {"boundaries": [{"page": 0, "system": 0, "source": "manual", "provenance": {}}]}
        )

    old_final = tmp_path / "old_numbering_final.json"
    write_json(old_final, {"pages": [{"systems": [{"measures": [{"number": 9}]}]}]})
    assert (
        persisted_final_next_number(
            old_final,
            expected_start_number=10,
            expected_boundaries=[],
        )
        is None
    )


def test_issue268_manual_override_rebases_without_mmr_payload() -> None:
    payload = {"measure_overrides": [{"page": 2, "system": 1, "measure": 0, "set_number": 42}]}

    rebased = rebase_mmr_overrides_to_page_local(payload, page_index=2)

    assert rebased["measure_overrides"] == [
        {"page": 0, "system": 1, "measure": 0, "set_number": 42}
    ]
    assert payload["measure_overrides"][0]["page"] == 2


def test_issue268_skip_existing_reuses_persisted_score_state(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    page_ids = ["page_001", "page_002"]
    images = [tmp_path / f"{page_id}.png" for page_id in page_ids]
    resolved = []
    page_ctx = {}
    for index, (page_id, image_path) in enumerate(zip(page_ids, images), start=1):
        barlines_path = tmp_path / f"{page_id}_barlines.json"
        write_json(barlines_path, [])
        page_intermediate = run_dir / "intermediate" / page_id
        page_outputs = run_dir / "outputs" / page_id
        page_intermediate.mkdir(parents=True)
        page_outputs.mkdir(parents=True)
        resolved_item = {
            "barlines_json": str(barlines_path),
            "staff_mask": str(tmp_path / f"{page_id}_staff_mask.png"),
        }
        resolved.append(resolved_item)
        page_ctx[page_id] = {
            "index": index,
            "image_path": image_path,
            "resolved": resolved_item,
            "intermediate_dir": page_intermediate,
            "outputs_dir": page_outputs,
            "barlines_path": barlines_path,
        }

    monkeypatch.setattr(image_utils, "load_image", lambda _path: _FakeImage())
    first = PipelineOrchestrator(
        {"steps": {"apply_measure_overrides": True}},
        run_id="issue268-first",
        run_dir=run_dir,
    )
    first._persistence = {"numbering_pipeline": _FakeNumberingPipeline()}
    first_paths = first.run_final_numbering_and_overlays(
        page_ids,
        set(),
        page_ctx,
        None,
    )

    class _UnexpectedRebuild(_FakeNumberingPipeline):
        def process_page(self, *_args, **_kwargs):
            raise AssertionError("skip_existing must not rebuild a matching final artifact")

    second = PipelineOrchestrator(
        {"steps": {"apply_measure_overrides": True}},
        run_id="issue268-second",
        run_dir=run_dir,
        skip_existing=True,
    )
    second._persistence = {"numbering_pipeline": _UnexpectedRebuild()}
    second_paths = second.run_final_numbering_and_overlays(page_ids, set(), page_ctx, None)

    assert [load_json(path) for path in second_paths] == [load_json(path) for path in first_paths]
