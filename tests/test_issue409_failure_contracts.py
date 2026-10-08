"""Failures stay failures through worker, parent and public engine boundaries."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

from src.pipeline.detection import current_support_worker as support
from src.pipeline.detection import maintained_source_page_worker as source
from src.pipeline.engine_contract import JobRequest, JobStatus, OutputProfile, ProgressKind
from src.pipeline.engine_executor import PipelineJobExecutor
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.steps.probe_scan import _load_bands_for_image

# Runs in a real child process. The production helper and SR worker remain the code under test.
SR_FAULT_SCRIPT = r"""
import builtins, contextlib, json, sys, types
from pathlib import Path
import numpy as np
from src.common import preprocessing as pre
from src.pipeline.detection import current_sr_worker as worker
stage = STAGE
pre._perf_span = lambda *a, **k: contextlib.nullcontext()
if stage == "import":
    original_import = builtins.__import__
    def fail_import(name, *a, **k):
        if name == "realesrgan": raise ImportError("injected SR import failure")
        return original_import(name, *a, **k)
    builtins.__import__ = fail_import
else:
    torch = types.ModuleType("torch")
    torch.device = lambda value: value
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    sys.modules['torch'] = torch
    rrdb = types.ModuleType('basicsr.archs.rrdbnet_arch')
    rrdb.RRDBNet = lambda **kwargs: object()
    sys.modules['basicsr.archs.rrdbnet_arch'] = rrdb
    sr = types.ModuleType('realesrgan')
    class FakeSR:
        def __init__(self, **kwargs):
            if stage == 'initialization': raise RuntimeError('injected SR initialization failure')
        def enhance(self, image, **kwargs):
            if stage == 'inference': raise RuntimeError('injected SR inference failure')
            if stage == 'shape': return image, None
            return np.repeat(np.repeat(image,4,axis=0),4,axis=1), None
    sr.RealESRGANer = FakeSR
    sys.modules['realesrgan'] = sr
    weight = Path(WEIGHT)
    def resolve(*args, **kwargs):
        if stage == 'model': raise FileNotFoundError('injected SR model resolution failure')
        return weight
    pre.resolve_realesrgan_weight = resolve
sys.argv = [sys.argv[0], *sys.argv[3:]]
raise SystemExit(worker.main())
"""


def _image(tmp_path):
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), np.full((8, 10, 3), 255, np.uint8))
    return path


def _engine(tmp_path, operation):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    with fitz.open() as doc:
        doc.new_page(width=100, height=100)
        doc.save(inputs / "score.pdf")
    config = tmp_path / "base.yaml"
    config.write_text("inputs:\n  pdf_to_images:\n    dpi: 72\n")

    def runner(*args, **kwargs):
        operation()
        raise AssertionError("failure operation returned success")

    executor = PipelineJobExecutor(
        input_root=inputs,
        artifact_root=tmp_path / "artifacts",
        base_config_path=config,
        source_commit="test",
        job_id_factory=lambda: "failed-job",
        pipeline_runner=runner,
    )
    events = []
    result = executor(
        JobRequest(
            input={"kind": "local_path", "reference": "score.pdf"},
            output_profile=OutputProfile.REVIEW,
        ),
        on_progress=events.append,
    )
    assert result.status is JobStatus.FAILED and result.artifacts == ()
    assert events[-1].kind is ProgressKind.JOB_FAILED
    package = tmp_path / "artifacts/failed-job"
    assert not (package / "final").exists() and not (package / "review").exists()
    assert not (package / ".engine-work").exists()
    return result


@pytest.mark.parametrize("stage", ["import", "model", "initialization", "inference", "shape"])
def test_sr_failure_is_nonzero_parent_error_and_failed_job(tmp_path, monkeypatch, stage):
    image = _image(tmp_path)
    weight = tmp_path / "weights.pth"
    weight.touch()
    shim = tmp_path / "sr_fault.py"
    shim.write_text(
        SR_FAULT_SCRIPT.replace("STAGE", repr(stage)).replace("WEIGHT", repr(str(weight)))
    )
    monkeypatch.setattr(support, "get_pipeline_python", lambda step: [sys.executable, str(shim)])
    result_path = tmp_path / "sr-result.json"
    log = tmp_path / "worker.log"

    def operation():
        support._run_child_worker(
            name="Current x4 SR",
            module="src.pipeline.detection.current_sr_worker",
            request={
                "image": str(image),
                "output": str(tmp_path / "sr.png"),
                "detection": {"sr_scale": 4},
            },
            request_path=tmp_path / "request.json",
            result_path=result_path,
            log_path=log,
            python_step="sr",
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )

    result = _engine(tmp_path, operation)
    assert result.failure is not None
    assert '"status": "failed"' in log.read_text()
    assert not result_path.exists() and not (tmp_path / "sr.png").exists()


@pytest.mark.parametrize("value", ["missing", None, [], {}, {"sr_scale": 2}])
@pytest.mark.parametrize("worker", [support, source])
def test_batch_mode_rejects_missing_null_invalid_before_heavy_work(
    tmp_path, monkeypatch, value, worker
):
    image = _image(tmp_path)
    request = {
        "image": str(image),
        "output_root": str(tmp_path / "support"),
        "baseline_output": str(tmp_path / "baseline"),
        "support_output": str(tmp_path / "support"),
        "project_root": str(tmp_path),
        "profile_name": "maintained_original",
        "run_id": "test",
        "detection": {"sr_scale": 4},
    }
    if value != "missing":
        request["precomputed_sr"] = value
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    monkeypatch.setattr(worker, "_load_request", lambda path: request)
    if worker is support:
        monkeypatch.setattr(
            worker, "_run_child_worker", lambda **k: pytest.fail("heavy child started")
        )
    else:
        monkeypatch.setattr(
            worker,
            "BatchSRVerifiedProfileHybridDetector",
            lambda **k: pytest.fail("baseline started"),
        )
    _engine(tmp_path, lambda: worker.run(path, tmp_path / "result.json"))
    assert not (tmp_path / "result.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        "{}",
        '{"predictions":{}}',
        "[[1,2,3]]",
        '[[0,0,"4",5]]',
        "[[0,0,NaN,5]]",
        "[[4,0,1,5]]",
        '[{"barline_location":[0,0,1,2]},{}]',
    ],
)
def test_invalid_component_json_fails_job_instead_of_empty_prediction(tmp_path, payload):
    path = tmp_path / "component.json"
    path.write_text(payload)

    def operation():
        with pytest.raises(ValueError, match="component.json"):
            load_json_boxes(path)
        load_json_boxes(path)

    _engine(tmp_path, operation)


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        '{"predictions":[]}',
        "[[0,0,4,5]]",
        '[{"barline_location":[0,0,4,5]}]',
        '{"predictions":[{"orig_bbox":[0,0,4,5]}]}',
    ],
)
def test_valid_empty_and_supported_prediction_schemas(tmp_path, payload):
    path = tmp_path / "valid.json"
    path.write_text(payload)
    assert load_json_boxes(path) == (
        [] if payload in ["[]", '{"predictions":[]}'] else [(0, 0, 4, 5)]
    )


def test_required_rescue_seed_missing_fails_job_but_optional_remains_allowed(tmp_path):
    args = dict(bands_from=tmp_path / "seeds", current_score_name="Score", stem="page_001")
    assert _load_bands_for_image(**args) == []
    _engine(tmp_path, lambda: _load_bands_for_image(**args, require_seed=True))
    with pytest.raises(FileNotFoundError, match="Score/page_001"):
        _load_bands_for_image(**args, require_seed=True)
    seed = tmp_path / "seeds/Score/page_001/pipeline2_no_peak_candidates.json"
    seed.parent.mkdir(parents=True)
    seed.write_text("[]")
    assert _load_bands_for_image(**args, require_seed=True) == []
    seed.write_text("{broken")
    with pytest.raises(ValueError, match="pipeline2_no_peak_candidates.json"):
        _load_bands_for_image(**args, require_seed=True)


def test_explicit_develop_modes_preserve_optional_compatibility(tmp_path):
    image = _image(tmp_path)
    assert support._require_precomputed_sr({"sr_mode": "page_local"}, image=image) is None
    path = tmp_path / "broken.json"
    path.write_text("{broken")
    assert load_json_boxes(path, strict=False) == []


@pytest.mark.parametrize("role", ["baseline", "current", "omr"])
@pytest.mark.parametrize("payload", ["{broken", '{"unexpected":[]}'])
def test_canonical_consensus_rejects_corrupt_homr_or_omr(tmp_path, monkeypatch, role, payload):
    from src.pipeline.detection.profile_sources import ProfileHybridDetector

    image = _image(tmp_path)
    detector = ProfileHybridDetector(
        det_cfg={"sr_scale": 4, "enable_sr": True, "hybrid_output_root": str(tmp_path / "hybrid")},
        images=[image],
        run_id="test",
        project_root=tmp_path,
        dry_run=False,
        skip_existing=False,
        profile_name="maintained_original",
    )

    def sources(*, baseline_output, support_output):
        paths = {
            "baseline": baseline_output / "batch" / image.stem / (image.stem + "_detections.json"),
            "current": support_output / "current.json",
            "omr": support_output / "omr.json",
        }
        for key, path in paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload if key == role else "[]")
        return {image: paths["current"]}, {image: paths["omr"]}, []

    monkeypatch.setattr(detector, "_generate_page_sources", sources)
    _engine(tmp_path, detector.run)
    assert not (tmp_path / "hybrid/test/hybrid_results" / f"{image.stem}_hybrid.json").exists()


def test_explicit_develop_source_page_mode_remains_available(tmp_path, monkeypatch):
    image = _image(tmp_path)
    captured = {}

    class DevDetector:
        def __init__(self, **kwargs):
            captured["class"] = "dev"

        def _generate_one_page_sources_in_process(self, **kwargs):
            captured.update(kwargs)
            return {}

    monkeypatch.setattr(source, "VerifiedProfileHybridDetector", DevDetector)
    request = tmp_path / "dev-request.json"
    request.write_text(
        json.dumps(
            {
                "image": str(image),
                "baseline_output": str(tmp_path / "base"),
                "support_output": str(tmp_path / "support"),
                "project_root": str(tmp_path),
                "run_id": "dev",
                "profile_name": "maintained_original",
                "sr_mode": "page_local",
                "detection": {"sr_scale": 4},
            }
        )
    )
    result = tmp_path / "dev-result.json"
    source.run(request, result)
    assert captured["class"] == "dev" and "precomputed_sr" not in captured
    assert json.loads(result.read_text())["sr_execution_scope"] == "page_subprocess"


def test_generic_sr_tolerant_import_contract_stays_explicit(tmp_path, monkeypatch):
    import builtins

    from src.common.preprocessing import apply_advanced_sr

    original = builtins.__import__

    def fail(name, *args, **kwargs):
        if name == "realesrgan":
            raise ImportError("injected")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail)
    image = np.zeros((8, 10, 3), np.uint8)
    returned, _ = apply_advanced_sr(image, strict=False)
    assert returned is image
    with pytest.raises(ImportError, match="injected"):
        apply_advanced_sr(image, strict=True)


BATCH_FAULT_SCRIPT = r"""
import builtins, sys, types
from src.pipeline.detection import current_sr_batch_worker as worker
stage=STAGE
if stage=='import':
    original=builtins.__import__
    def fail(name,*a,**k):
        if name=='src.pipeline.detection.current_sr_runtime':
            raise ImportError('injected batch SR import failure')
        return original(name,*a,**k)
    builtins.__import__=fail
else:
    class Runtime:
        def __init__(self,**kwargs):
            if stage=='model': raise FileNotFoundError('injected SR model resolution failure')
            if stage=='initialization': raise RuntimeError('injected SR initialization failure')
            self.torch=types.SimpleNamespace(cuda=types.SimpleNamespace(reset_peak_memory_stats=lambda:None))
        def enhance(self,image):
            if stage=='inference': raise RuntimeError('injected SR inference failure')
            return image
    module=types.ModuleType('src.pipeline.detection.current_sr_runtime')
    module.CurrentX4SRRuntime=Runtime
    sys.modules[module.__name__]=module
sys.argv=[sys.argv[0],*sys.argv[3:]]
raise SystemExit(worker.main())
"""


@pytest.mark.parametrize("stage", ["import", "model", "initialization", "inference", "shape"])
def test_batch_sr_failure_propagates_through_actual_batch_parent(tmp_path, monkeypatch, stage):
    from src.pipeline.detection import profile_sources_batch_sr as batch

    image = _image(tmp_path)
    shim = tmp_path / "batch_fault.py"
    shim.write_text(BATCH_FAULT_SCRIPT.replace("STAGE", repr(stage)))
    monkeypatch.setattr(batch, "get_pipeline_python", lambda step: [sys.executable, str(shim)])
    detector = batch.BatchSRProfileHybridDetector(
        det_cfg={"sr_scale": 4, "enable_sr": True},
        images=[image],
        run_id="test",
        project_root=Path(__file__).resolve().parents[1],
        dry_run=False,
        skip_existing=False,
        profile_name="maintained_original",
    )
    support_root = tmp_path / "support"
    _engine(tmp_path, lambda: detector._batch_sr_worker(support_output=support_root))
    assert '"status": "failed"' in (support_root / "_sr_batch/worker.log").read_text()
    assert not (support_root / "_sr_batch/result.json").exists()
