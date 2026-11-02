import json
import sys

import pytest

from tools.issue459 import matrix


@pytest.mark.parametrize("failed_cell", [1, None])
def test_remaining_matrix_stops_at_failed_gate_without_retry(tmp_path, monkeypatch, failed_cell):
    primary = tmp_path / "primary.json"
    primary.write_text(json.dumps({"primary_gate": "passed"}))
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
