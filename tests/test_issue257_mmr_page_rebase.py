from copy import deepcopy
from pathlib import Path

import src.pipeline.orchestrator as orchestrator_module
import src.pipeline.utils.images as image_utils
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Staff, System
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.steps.numbering import rebase_mmr_overrides_to_page_local
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
        [1, 2, 3, 4],
        [1, 2, 4, 5],
    ]
    per_page_payloads = []
    for page_index, page_id in enumerate(page_ids):
        overrides_path = run_dir / "intermediate" / page_id / "overrides_mmr.json"
        assert load_json(overrides_path) == persisted_payload

        final_path = run_dir / "outputs" / page_id / "numbering_final.json"
        final_payload = load_json(final_path)
        per_page_payloads.append(final_payload)
        assert final_payload["pages"][0]["page_number"] == page_index + 1
        measures = final_payload["pages"][0]["systems"][0]["measures"]
        assert [measure["number"] for measure in measures] == expected_numbers[page_index]

    combined_payload = load_json(run_dir / "outputs" / "numbering_final.json")
    assert combined_payload["pages"] == [payload["pages"][0] for payload in per_page_payloads]
