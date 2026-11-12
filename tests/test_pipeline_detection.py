"""Single detector route contract (#522): dense_full_pipeline only, removed routes fail."""

import json
from pathlib import Path

import fitz
import pytest

from src.pipeline import detection
from src.pipeline.core import write_yaml
from src.pipeline.detection import dense_orchestrator_batch_sr
from src.pipeline.detection.config import DENSE_ROUTE_NAME, resolve_detector_route
from src.pipeline.main import run_pipeline
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


def test_correction_of_a_standard_route_review_package_is_not_rejected(tmp_path):
    # Correction never reruns detection: the recorded route of a historical source run
    # is provenance, so packages produced by the removed standard route stay correctable.
    from src.pipeline.review.apply_corrections import _run_retained_artifact_correction

    canonical = {
        "measure_overrides": tmp_path / "measure_overrides.json",
        "barline_overrides": tmp_path / "barline_overrides.json",
    }
    summary = _run_retained_artifact_correction(
        normalized_handoff={"pages": []},
        package_root=tmp_path,
        source_manifest={"pages": []},
        source_root=tmp_path,
        source_config={"detection": {"detector_route": "standard"}},
        canonical_paths=canonical,
        staging_paths={},
        new_run_dir=tmp_path / "corrected",
        movement_boundary_input=({}, None, None),
    )
    assert isinstance(summary, dict)


def test_synthetic_pdf_reaches_manifest_with_detector_outputs(tmp_path, monkeypatch):
    pdf = tmp_path / "score.pdf"
    with fitz.open() as document:
        document.new_page(width=144, height=180)
        document.save(pdf)

    calls = []

    def detector(config, images, page_ids, run_id, run_dir, *, dry_run, in_memory_images):
        assert page_ids == ["page_001"]
        assert len(images) == 1 and images[0].is_file()
        assert not dry_run and in_memory_images is None
        calls.append("detector")
        probe = run_dir / "synthetic_probe"
        hybrid = run_dir / "synthetic_hybrid"
        result = hybrid / "hybrid_results" / "page_001_hybrid.json"
        result.parent.mkdir(parents=True)
        result.write_text('{"barlines": []}', encoding="utf-8")
        probe.mkdir()
        return {
            "commands": [["synthetic-detector"]],
            "probe_output_dir": probe,
            "hybrid_output_dir": hybrid,
        }

    monkeypatch.setattr("src.pipeline.orchestrator.run_detection_step", detector)
    config = {
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "1", "dpi": 72}},
        "steps": {"pdf_to_images": True, "detection": True},
        "detection": {"homr_profile": "maintained_original", "staff_mask_dir": None},
    }
    config_path = tmp_path / "config.yaml"
    write_yaml(config_path, config)
    run_dir = run_pipeline(config_path, run_id="synthetic", output_root=tmp_path / "runs")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert calls == ["detector"]
    assert (run_dir / "inputs/images/page_001.png").is_file()
    assert len(manifest["pages"]) == 1
    assert "synthetic-detector" in json.dumps(manifest)
    assert "page_001_hybrid.json" in json.dumps(manifest)


@pytest.mark.parametrize("scenario", ["disabled", "missing", "available"])
def test_real_integration_opt_in_dependency_gate(tmp_path, scenario):
    """Exercise collection and class setup without loading a model or touching a GPU."""
    import os
    import subprocess
    import sys

    plugin = tmp_path / "integration_gate_probe.py"
    plugin.write_text(
        """import importlib.util
import os
from pathlib import Path

_original = importlib.util.find_spec

def pytest_collection_modifyitems(items):
    scenario = os.environ["INTEGRATION_GATE_SCENARIO"]
    def find_spec(name, *args, **kwargs):
        if name == "homr":
            return object() if scenario == "available" else None
        return _original(name, *args, **kwargs)
    importlib.util.find_spec = find_spec
    if scenario == "available":
        def stop_before_pipeline(config_path):
            assert Path(config_path).is_file()
            assert Path(config_path).parent.name.startswith("pdfscore-integration-")
            raise RuntimeError("TEST_REACHED_PIPELINE_WITH_ISOLATED_CONFIG")
        items[0].module.run_pipeline = stop_before_pipeline
""",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(root)])
    env["INTEGRATION_GATE_SCENARIO"] = scenario
    env.pop("PDFSCORE_RUN_REAL_INTEGRATION", None)
    if scenario != "disabled":
        env["PDFSCORE_RUN_REAL_INTEGRATION"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            "-p",
            "integration_gate_probe",
            "tests/test_pipeline_integration.py::TestPipelineIntegration::test_full_sequence",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    if scenario == "disabled":
        assert result.returncode == 0 and "1 skipped" in output
        assert "requires explicit opt-in" in output
    elif scenario == "missing":
        assert result.returncode != 0
        assert "Real PDF integration requires HOMR" in output
        assert "1 skipped" not in output
    else:
        assert result.returncode != 0
        assert "TEST_REACHED_PIPELINE_WITH_ISOLATED_CONFIG" in output
        assert "1 skipped" not in output
