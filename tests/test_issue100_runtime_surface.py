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


def test_production_omr_worker_is_under_src() -> None:
    support = (PROJECT_ROOT / "src/pipeline/detection/current_support_worker.py").read_text(
        encoding="utf-8"
    )
    assert "src.pipeline.detection.omr_dln_worker" in support
    assert "experiments/models/eval_omr_dln.py" not in support


@pytest.mark.parametrize(
    "missing_path",
    [
        "tools/movement_boundary_review.py",
        "src/pipeline/review/movement_boundary_review.py",
        "docs/ENGINE_JOB_LIFECYCLE.md",
        "docs/ENGINE_INPUT_SAFETY.md",
        "docs/ENGINE_TELEMETRY.md",
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
    assert f"documented tracked pattern has no matches: {missing_path}" in capsys.readouterr().err
