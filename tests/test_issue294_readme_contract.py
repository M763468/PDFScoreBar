from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issue294_readme_keeps_gt_and_model_lineage_gates_explicit() -> None:
    text = (PROJECT_ROOT / "tools/issue294/README.md").read_text(encoding="utf-8")

    assert "A-vs-B is a whole candidate-stack comparison, not a runtime-only" in text
    assert "evaluate_existing_ab_gt_host.py" in text
    assert "performs no HOMR inference" in text
    assert "not the final Stage-E CNN metric" in text
