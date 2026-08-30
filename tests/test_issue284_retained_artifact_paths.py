import json
from pathlib import Path

import pytest

from tools.issue284.compare_full68_variants import resolve_retained_path, support_semantics


def test_comparator_resolves_relocated_variant_artifact(tmp_path: Path) -> None:
    variant = tmp_path / "issue284_compile_full68_01_eager"
    artifact = variant / "Score" / "hybrid_output" / "page_001_hybrid.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("[]\n", encoding="utf-8")

    recorded = Path(
        "/workspace/logs/issue284/issue284_compile_full68_01_eager/"
        "Score/hybrid_output/page_001_hybrid.json"
    )

    assert resolve_retained_path(recorded, variant_root=variant) == artifact.resolve()


def test_comparator_prefers_requested_variant_over_existing_recorded_path(tmp_path: Path) -> None:
    variant_name = "issue284_compile_full68_01_eager"
    variant = tmp_path / "relocated" / variant_name
    relocated = variant / "Score" / "hybrid_output" / "page_001_hybrid.json"
    relocated.parent.mkdir(parents=True)
    relocated.write_text("relocated\n", encoding="utf-8")

    recorded = (
        tmp_path / "original" / variant_name / "Score" / "hybrid_output" / "page_001_hybrid.json"
    )
    recorded.parent.mkdir(parents=True)
    recorded.write_text("stale\n", encoding="utf-8")

    assert resolve_retained_path(recorded, variant_root=variant) == relocated.resolve()


def test_support_semantics_rejects_missing_declared_connector_artifact(tmp_path: Path) -> None:
    variant = tmp_path / "issue284_compile_full68_01_eager"
    support = variant / "Score" / "current_support" / "page_001" / "result.json"
    support.parent.mkdir(parents=True)

    symbols = variant / "Score" / "artifacts" / "connector_symbols.png"
    brace_dot = variant / "Score" / "artifacts" / "connector_brace_dot.png"
    brace_dot.parent.mkdir(parents=True)
    brace_dot.write_bytes(b"brace-dot")

    support.write_text(
        json.dumps(
            {
                "connector_complete": True,
                "historical_detector_artifact_runtime_input": False,
                "connector_symbols": str(symbols),
                "connector_brace_dot": str(brace_dot),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="Retained artifact not found"):
        support_semantics(support, variant_root=variant)


def test_support_semantics_rejects_missing_required_connector_field(tmp_path: Path) -> None:
    variant = tmp_path / "issue284_compile_full68_01_eager"
    support = variant / "Score" / "current_support" / "page_001" / "result.json"
    support.parent.mkdir(parents=True)

    brace_dot = variant / "Score" / "artifacts" / "connector_brace_dot.png"
    brace_dot.parent.mkdir(parents=True)
    brace_dot.write_bytes(b"brace-dot")

    support.write_text(
        json.dumps(
            {
                "connector_complete": True,
                "historical_detector_artifact_runtime_input": False,
                "connector_brace_dot": str(brace_dot),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="connector_symbols"):
        support_semantics(support, variant_root=variant)
