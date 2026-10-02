import ast
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from src.homr_runtime.filtering import (
    count_staff_crossings,
    filter_detections_by_notehead_proximity,
)
from src.homr_runtime.types import BarlinePrediction, TransformInfo
from src.pipeline.detection import maintained_profile
from src.pipeline.detection.maintained_profile_hybrid import (
    BatchSRVerifiedProfileHybridDetector,
)
from tools.check_repository_surface import local_import_targets


def test_surface_check_resolves_relative_imports_and_package_initializers():
    tracked = {
        "src/homr_runtime/__init__.py",
        "src/homr_runtime/types.py",
        "src/homr_eval_scripts/__init__.py",
        "src/homr_eval_scripts/core/__init__.py",
        "src/homr_eval_scripts/core/predictor.py",
    }
    imports = ast.parse(
        "from .types import BarlinePrediction\nfrom src.homr_eval_scripts.core import predictor\n"
    )
    assert local_import_targets("src/homr_runtime/reporting.py", imports, tracked) == tracked


def test_surface_check_finds_lazy_runtime_leaks_but_ignores_external_modules():
    imports = ast.parse(
        "import homr.main\ndef run():\n    from ..homr_eval_scripts.core import predictor\n"
    )
    tracked = {"src/homr_eval_scripts/core/predictor.py"}
    assert local_import_targets("src/homr_runtime/predictor.py", imports, tracked) == tracked


def test_legacy_heuristics_adapter_preserves_actual_consumer_patch_points(monkeypatch):
    # All substituted modules are scoped by monkeypatch; no HOMR import or global
    # model stubs remain after this test.
    runtime = ModuleType("src.homr_runtime.heuristics")
    exec(
        "load_and_preprocess_predictions = lambda: 'original'\n"
        "def detect_staffs_with_barlines():\n"
        "    return load_and_preprocess_predictions()\n",
        runtime.__dict__,
    )
    ends = ModuleType("src.homr_runtime.end_barlines")
    ends._cluster_by_y_centers = lambda: None
    ends._scan_vertical_line = lambda: None
    diagnostics = ModuleType("src.homr_eval_scripts.core.diagnostics")
    for name in (
        "resolve_clusters_dry_run",
        "resolve_tight_duplicates_dry_run",
        "export_measure_grid_candidates",
        "compute_candidate_stats",
        "compute_and_save_gap_stats",
    ):
        setattr(diagnostics, name, lambda: None)
    runtime_package = importlib.import_module("src.homr_runtime")
    core_package = importlib.import_module("src.homr_eval_scripts.core")
    monkeypatch.setattr(runtime_package, "heuristics", runtime, raising=False)
    monkeypatch.setattr(core_package, "diagnostics", diagnostics, raising=False)
    for module in (runtime, ends, diagnostics):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    name = "src.homr_eval_scripts.core._issue115_adapter_test"
    path = Path(__file__).resolve().parents[1] / "src/homr_eval_scripts/core/heuristics.py"
    spec = importlib.util.spec_from_file_location(name, path)
    adapter = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, adapter)
    spec.loader.exec_module(adapter)
    legacy = sys.modules[name]
    assert legacy is runtime
    legacy.load_and_preprocess_predictions = lambda: "patched"
    assert runtime.detect_staffs_with_barlines() == "patched"
    assert legacy.compute_candidate_stats is diagnostics.compute_candidate_stats


def test_filtering_preserves_prediction_identity_and_partition():
    mask = np.zeros((40, 30), np.uint8)
    mask[10:20, 10:12] = 255
    small = BarlinePrediction((10, 10, 12, 20), (10, 10, 12, 20), 0, 0)
    tall = BarlinePrediction((10, 0, 12, 35), (10, 0, 12, 35), 0, 0)
    outside = BarlinePrediction((50, 0, 52, 10), (50, 0, 52, 10), 1, 1)
    kept, rejected = filter_detections_by_notehead_proximity(
        [small, tall, outside], mask, 5, 5, 24, 4
    )
    assert kept == [tall, outside]
    assert kept[0] is tall
    assert rejected == [small]


def test_staff_crossings_count_contiguous_lines_and_clamp_to_image():
    mask = np.zeros((30, 12), np.uint8)
    mask[2:4] = 255
    mask[10:12] = 255
    mask[20:22] = 255
    assert count_staff_crossings((4, -10, 6, 40), mask) == 3
    assert count_staff_crossings((4, 8, 6, 15), mask) == 1
    assert count_staff_crossings((40, 0, 42, 30), mask) == 0


def test_transform_record_preserves_anisotropic_total_scale():
    transform = TransformInfo(
        (100, 200), (10, 20, 70, 150), (140, 300), (70, 75), (2, 2), (0.5, 0.25)
    )
    assert transform.total_scale == (1.0, 0.5)


def test_maintained_backend_rejects_historical_execution_without_loading_it(tmp_path):
    with pytest.raises(ValueError, match="Unsupported maintained"):
        maintained_profile.run_homr_profile(
            "stage_e_verified", images=[Path("image.png")], output_root=tmp_path
        )


def test_maintained_batch_workflow_uses_its_own_worker_and_backend(tmp_path, monkeypatch):
    detector = BatchSRVerifiedProfileHybridDetector(
        det_cfg={"sr_scale": 4},
        images=[],
        run_id="contract",
        project_root=tmp_path,
        dry_run=True,
        skip_existing=False,
        profile_name="maintained_original",
    )
    import src.pipeline.detection.maintained_profile_hybrid as module

    seen = []
    monkeypatch.setattr(
        module, "run_homr_profile", lambda *args, **kwargs: seen.append(args) or {"commands": []}
    )
    assert detector.source_worker_module == "src.pipeline.detection.maintained_source_page_worker"
    assert detector._run_homr_profile("maintained_original", images=[], output_root=tmp_path) == {
        "commands": []
    }
    assert seen == [("maintained_original",)]


@pytest.mark.parametrize("batch", [False, True])
def test_dense_dispatch_preserves_explicit_historical_profile(tmp_path, monkeypatch, batch):
    if batch:
        import src.pipeline.detection.dense_orchestrator_batch_sr as dense
        import src.pipeline.detection.profile_hybrid_batch_sr as historical

        name = "BatchSRVerifiedProfileHybridDetector"
    else:
        import src.pipeline.detection.dense_orchestrator as dense
        import src.pipeline.detection.profile_hybrid as historical

        name = "VerifiedProfileHybridDetector"
    seen = []

    class HistoricalDetector:
        def __init__(self, **kwargs):
            seen.append(kwargs["profile_name"])

        def run(self):
            return {"profile": "stage_e_verified"}

    monkeypatch.setattr(historical, name, HistoricalDetector)
    state = SimpleNamespace(
        homr_profile="stage_e_verified",
        det_cfg={},
        images=[],
        run_id="compatibility",
        dry_run=True,
        skip_existing=False,
        in_memory_images=None,
    )
    assert dense.DetectorOrchestrator._run_hybrid_detection(state) == {
        "profile": "stage_e_verified"
    }
    assert seen == ["stage_e_verified"]


def test_batch_workflows_preserve_profile_detector_subclass_contract():
    from src.pipeline.detection import (
        maintained_profile_hybrid,
        profile_hybrid,
        profile_hybrid_batch_sr,
    )

    assert issubclass(
        profile_hybrid_batch_sr.BatchSRVerifiedProfileHybridDetector,
        profile_hybrid.VerifiedProfileHybridDetector,
    )
    assert issubclass(
        maintained_profile_hybrid.BatchSRVerifiedProfileHybridDetector,
        maintained_profile_hybrid.VerifiedProfileHybridDetector,
    )
