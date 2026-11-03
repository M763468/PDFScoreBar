import json
import sys

import pytest

from tools.issue459 import matrix

PASSED_PRIMARY = {
    "primary_gate": "passed",
    "baseline_median": 100.0,
    "candidate_median": 96.0,
    "cell": {
        "uid": 0,
        "scope": "multi",
        "compiler_state": "warm",
        "minimum_improvement_percent": 3,
    },
}


@pytest.mark.parametrize("failed_cell", [1, None])
def test_remaining_matrix_stops_at_failed_gate_without_retry(tmp_path, monkeypatch, failed_cell):
    primary = tmp_path / "primary.json"
    primary.write_text(json.dumps(PASSED_PRIMARY))
    monkeypatch.setattr(matrix, "__file__", str(tmp_path / "tools/issue459/matrix.py"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "matrix",
            "--image",
            "sha256:" + "a" * 64,
            "--seed",
            str(tmp_path),
            "--primary",
            str(primary),
            "--label",
            "fixed",
        ],
    )
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        label = command[command.index("--label") + 1]
        out = tmp_path / "logs/issue459/screens" / label
        out.mkdir(parents=True)
        (out / "summary.json").write_text(
            json.dumps({"primary_gate": "failed" if len(calls) == failed_cell else "passed"})
        )

    monkeypatch.setattr(matrix.subprocess, "run", execute)
    matrix.main()
    expected = 1 if failed_cell else 7
    assert len(calls) == expected
    assert len({c[c.index("--label") + 1] for c in calls}) == expected
    assert calls[0][calls[0].index("--compiler-state") + 1] == "cold"
    result = json.loads((tmp_path / "logs/issue459/matrices/fixed/results.json").read_text())
    assert result["remaining_cells"] == 7 - expected
    assert result["adoption"] == (
        "rejected_required_performance_gate"
        if failed_cell
        else "pending_quality_and_recovery_gates"
    )


def _run_with_primary(tmp_path, monkeypatch, summary):
    primary = tmp_path / "primary.json"
    primary.write_text(json.dumps(summary))
    monkeypatch.setattr(matrix, "__file__", str(tmp_path / "tools/issue459/matrix.py"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "matrix",
            "--image",
            "sha256:" + "a" * 64,
            "--seed",
            str(tmp_path),
            "--primary",
            str(primary),
            "--label",
            "fixed",
        ],
    )
    calls = []
    monkeypatch.setattr(matrix.subprocess, "run", lambda command, **kw: calls.append(command))
    return calls


@pytest.mark.parametrize(
    "cell",
    [
        # Non-primary cells use a -3% regression tolerance; a 2% regression "passes" them.
        {
            "uid": 1000,
            "scope": "single",
            "compiler_state": "cold",
            "minimum_improvement_percent": -3,
        },
        {"uid": 0, "scope": "multi", "compiler_state": "cold", "minimum_improvement_percent": -3},
        {"uid": 0, "scope": "single", "compiler_state": "warm", "minimum_improvement_percent": -3},
        {
            "uid": 1000,
            "scope": "multi",
            "compiler_state": "warm",
            "minimum_improvement_percent": -3,
        },
        {"uid": 0, "scope": "multi", "compiler_state": "warm", "minimum_improvement_percent": -3},
        {"uid": 0, "scope": "multi", "compiler_state": "warm", "minimum_improvement_percent": 2},
        None,
    ],
)
def test_matrix_rejects_non_primary_summary(tmp_path, monkeypatch, cell):
    summary = {
        "primary_gate": "passed",
        "baseline_median": 100.0,
        "candidate_median": 102.0,
        "candidate_protocol": "issue447-poc",
    }
    if cell is not None:
        summary["cell"] = cell
    calls = _run_with_primary(tmp_path, monkeypatch, summary)
    with pytest.raises(ValueError):
        matrix.main()
    assert calls == []
    assert not (tmp_path / "logs/issue459/matrices/fixed").exists()


def test_matrix_rejects_passed_label_contradicted_by_medians(tmp_path, monkeypatch):
    calls = _run_with_primary(
        tmp_path, monkeypatch, {**PASSED_PRIMARY, "candidate_median": 97.4348}
    )
    with pytest.raises(ValueError, match="medians"):
        matrix.main()
    assert calls == []


def test_matrix_rejects_failed_primary(tmp_path, monkeypatch):
    calls = _run_with_primary(tmp_path, monkeypatch, {**PASSED_PRIMARY, "primary_gate": "failed"})
    with pytest.raises(RuntimeError, match="primary screen failed"):
        matrix.main()
    assert calls == []
