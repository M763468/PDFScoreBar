from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _runtime_contract():
    module_path = PROJECT_ROOT / "docker" / "runtime_contract.py"
    spec = importlib.util.spec_from_file_location("issue100_runtime_contract", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_experiments_do_not_change_runtime_source_fingerprint(tmp_path: Path) -> None:
    runtime_contract = _runtime_contract()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    experiment = tmp_path / "experiments" / "models" / "probe.py"
    experiment.parent.mkdir(parents=True)
    experiment.write_text("VALUE = 1\n", encoding="utf-8")

    initial = runtime_contract.source_fingerprint(tmp_path)
    experiment.write_text("VALUE = 2\n", encoding="utf-8")

    assert runtime_contract.source_fingerprint(tmp_path) == initial


def test_production_support_does_not_run_omr_dln() -> None:
    support = (PROJECT_ROOT / "src/pipeline/detection/current_support_worker.py").read_text(
        encoding="utf-8"
    )
    assert "omr_dln_worker" not in support
    assert "experiments/models/eval_omr_dln.py" not in support
    assert not (PROJECT_ROOT / "src/pipeline/detection/omr_dln_worker.py").exists()


def test_omr_dln_and_the_standard_route_cannot_return() -> None:
    """#522: no OMR-DLN code path, setting, model manifest or Ultralytics dependency."""
    import yaml

    for config in ("configs/dense_full_pipeline.yaml", "configs/smoke_test.yaml"):
        detection = yaml.safe_load((PROJECT_ROOT / config).read_text())["detection"]
        assert not any(key.startswith("omr") for key in detection), config
    assert "ultralytics" not in (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    from src.pipeline.detection.config import DENSE_ROUTE_NAME, resolve_detector_route

    for config in sorted((PROJECT_ROOT / "configs").glob("*.yaml")):
        payload = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        assert resolve_detector_route(payload.get("detection")) == DENSE_ROUTE_NAME, config
    for removed in (
        "src/pipeline/detection/omr_dln_worker.py",
        "src/pipeline/detection/omr_job.py",
        "src/pipeline/detection/omr_job_worker.py",
        "models/omr_dln/manifest.json",
        "experiments/models/eval_omr_dln.py",
        "src/pipeline/detection/hybrid.py",
        "src/pipeline/detection/orchestrator.py",
    ):
        assert not (PROJECT_ROOT / removed).exists(), removed
    for module in (
        "src/pipeline/detection/current_support_worker.py",
        "src/pipeline/detection/profile_sources.py",
        "src/pipeline/detection/profile_sources_batch_sr.py",
        "src/pipeline/steps/staff_strokes.py",
        "src/pipeline/steps/probe_scan.py",
    ):
        text = (PROJECT_ROOT / module).read_text(encoding="utf-8")
        for token in ("omr_dln", "omr_sr", "current_omr", "omr_boxes", "ultralytics"):
            assert token not in text, (module, token)


@pytest.mark.parametrize(
    "missing_path",
    [
        "tools/movement_boundary_review.py",
        "src/pipeline/review/movement_boundary_review.py",
        "docs/contracts/ENGINE_JOB_LIFECYCLE.md",
        "docs/contracts/ENGINE_INPUT_SAFETY.md",
        "docs/contracts/ENGINE_TELEMETRY.md",
    ],
)
def test_surface_checker_rejects_missing_review_and_engine_contract_files(
    missing_path: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import check_repository_surface

    files = check_repository_surface.tracked_files()
    assert missing_path in files
    monkeypatch.setattr(
        check_repository_surface,
        "tracked_files",
        lambda: [path for path in files if path != missing_path],
    )

    assert check_repository_surface.main() == 1
    expected = (
        f"runtime bundle path is not tracked: {missing_path}"
        if missing_path.startswith("src/")
        else f"documented tracked pattern has no matches: {missing_path}"
    )
    assert expected in capsys.readouterr().err
