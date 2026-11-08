"""Single detector route contract (#522): dense_full_pipeline only, removed routes fail."""

from pathlib import Path

import pytest

from src.pipeline import detection
from src.pipeline.detection import dense_orchestrator_batch_sr
from src.pipeline.detection.config import DENSE_ROUTE_NAME, resolve_detector_route
from src.pipeline.orchestrator import PipelineOrchestrator


def _detection(**extra):
    return {"homr_profile": "maintained_original", **extra}


def test_omitted_route_selects_dense_full_pipeline():
    assert resolve_detector_route({}) == DENSE_ROUTE_NAME
    assert resolve_detector_route(None) == DENSE_ROUTE_NAME
    assert resolve_detector_route({"detector_route": DENSE_ROUTE_NAME}) == DENSE_ROUTE_NAME


@pytest.mark.parametrize("route", ["standard", "stage_e", ""])
def test_removed_or_unknown_routes_raise_instead_of_being_reinterpreted(route):
    with pytest.raises(ValueError, match="only detector route is 'dense_full_pipeline'"):
        resolve_detector_route({"detector_route": route})


def test_standard_route_error_names_migration_and_historical_commit():
    with pytest.raises(ValueError, match=r"was removed in #522.*4f1594bc"):
        resolve_detector_route({"detector_route": "standard"})


def test_public_constructor_always_builds_the_dense_orchestrator(tmp_path):
    orchestrator = detection.DetectorOrchestrator(
        {"detection": _detection()}, [], "run", tmp_path, dry_run=True
    )
    assert isinstance(orchestrator, dense_orchestrator_batch_sr.DetectorOrchestrator)
    assert orchestrator.detector_route == DENSE_ROUTE_NAME


def test_public_entrypoints_reject_standard_before_any_detector_work(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dense_orchestrator_batch_sr,
        "run_detection_step",
        lambda *a, **k: pytest.fail("dense detector entered for a removed route"),
    )
    config = {"detection": _detection(detector_route="standard")}
    with pytest.raises(ValueError, match="was removed in #522"):
        detection.DetectorOrchestrator(config, [], "run", tmp_path, dry_run=True)
    with pytest.raises(ValueError, match="was removed in #522"):
        detection.run_detection_step(config, [], [], "run", tmp_path, dry_run=True)


def test_run_detection_step_delegates_to_the_dense_route(tmp_path, monkeypatch):
    calls = []

    def dense(config, images, page_ids, run_id, run_dir, *, dry_run, in_memory_images=None):
        calls.append((images, page_ids, run_id, dry_run, in_memory_images))
        return {"detector_route": DENSE_ROUTE_NAME}

    monkeypatch.setattr(dense_orchestrator_batch_sr, "run_detection_step", dense)
    images = [tmp_path / "Score" / "page_001.png"]
    result = detection.run_detection_step(
        {"detection": _detection()}, images, ["page_001"], "run", tmp_path, dry_run=True
    )
    assert result == {"detector_route": DENSE_ROUTE_NAME}
    assert calls == [(images, ["page_001"], "run", True, None)]


def test_duplicate_image_stems_are_rejected(tmp_path):
    images = [tmp_path / "a" / "page_001.png", tmp_path / "b" / "page_001.png"]
    with pytest.raises(ValueError, match="unique image stems"):
        detection.run_detection_step(
            {"detection": _detection()}, images, ["a", "b"], "run", tmp_path, dry_run=True
        )


def _pipeline_config(**pdf_opts):
    return {
        "inputs": {"pdf_path": "missing.pdf", "pdf_to_images": dict(pdf_opts)},
        "steps": {"pdf_to_images": True, "detection": True},
        "detection": _detection(),
    }


def test_pipeline_rejects_removed_route_at_construction(tmp_path):
    config = _pipeline_config(output_dir="images")
    config["detection"]["detector_route"] = "standard"
    with pytest.raises(ValueError, match="was removed in #522"):
        PipelineOrchestrator(config, "run", tmp_path)


def test_in_memory_pdf_rendering_is_rejected_with_detection(tmp_path):
    with pytest.raises(ValueError, match="In-memory PDF rendering"):
        PipelineOrchestrator(_pipeline_config(output_dir=None), "run", tmp_path)


def test_in_memory_pdf_rendering_remains_available_without_detection(tmp_path):
    config = _pipeline_config(output_dir=None)
    config["steps"]["detection"] = False
    PipelineOrchestrator(config, "run", tmp_path)


def test_persisted_pdf_rendering_with_detection_is_accepted(tmp_path):
    PipelineOrchestrator(_pipeline_config(output_dir="images"), "run", tmp_path)
    PipelineOrchestrator(_pipeline_config(), "run", Path(tmp_path))


def _ctx(tmp_path, *mask_present):
    ctx = {}
    for index, present in enumerate(mask_present, start=1):
        mask = tmp_path / f"page_{index:03d}_staff_mask.png"
        if present:
            mask.write_bytes(b"mask")
        ctx[f"page_{index:03d}"] = {"resolved": {"current_homr_staff_mask": str(mask)}}
    return ctx


def test_mmr_support_is_required_after_detection_in_this_run(tmp_path):
    ctx = _ctx(tmp_path, False)
    assert PipelineOrchestrator._mmr_uses_current_x4_support(True, list(ctx), set(), ctx)


def test_precomputed_inputs_use_support_only_when_every_page_has_a_mask(tmp_path):
    full = _ctx(tmp_path, True, True)
    assert PipelineOrchestrator._mmr_uses_current_x4_support(False, list(full), set(), full)
    (tmp_path / "none").mkdir()
    none = _ctx(tmp_path / "none", False, False)
    assert not PipelineOrchestrator._mmr_uses_current_x4_support(False, list(none), set(), none)


def test_precomputed_inputs_with_partial_masks_are_rejected(tmp_path):
    ctx = _ctx(tmp_path, True, False)
    with pytest.raises(ValueError, match="only some pages"):
        PipelineOrchestrator._mmr_uses_current_x4_support(False, list(ctx), set(), ctx)
    # An excluded page without a mask does not make the set partial.
    assert PipelineOrchestrator._mmr_uses_current_x4_support(False, list(ctx), {"page_002"}, ctx)


def test_correction_reapplies_mmr_in_the_source_run_mode(tmp_path):
    from src.pipeline.review.apply_corrections import _source_used_mmr_support

    assert _source_used_mmr_support({"mmr_support": {}}, source_root=tmp_path, page_id="p")
    assert not _source_used_mmr_support({}, source_root=tmp_path, page_id="p")
    support = tmp_path / "intermediate" / "p" / "mmr_support.json"
    support.parent.mkdir(parents=True)
    support.write_text("{}")
    assert _source_used_mmr_support({}, source_root=tmp_path, page_id="p")
