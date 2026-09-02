from __future__ import annotations

from tools.issue294 import finalize_same_original_gate_host as finalizer
from tools.issue294 import run_same_original_ab_historical as historical_runner


def test_issue294_finalizer_recovers_null_source_commit_with_explicit_override(monkeypatch) -> None:
    checked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        finalizer,
        "_require_experiment_commit_ancestor",
        lambda experiment, current: checked.append((experiment, current)),
    )
    experiment = "9" * 40
    current = "a" * 40

    resolved, recovery = finalizer._resolve_experiment_commit(
        {"source_commit": None},
        experiment,
        current,
    )

    assert resolved == experiment
    assert recovery == {
        "required": True,
        "reason": "inner_runner_git_probe_returned_null",
        "summary_source_commit": None,
        "method": "explicit_known_experiment_head",
        "recovered_source_commit": experiment,
        "summary_mutated": False,
    }
    assert checked == [(experiment, current)]


def test_issue294_finalizer_does_not_override_existing_summary_commit(monkeypatch) -> None:
    monkeypatch.setattr(finalizer, "_require_experiment_commit_ancestor", lambda *_args: None)
    summary_commit = "8" * 40

    resolved, recovery = finalizer._resolve_experiment_commit(
        {"source_commit": summary_commit},
        None,
        "a" * 40,
    )

    assert resolved == summary_commit
    assert recovery is None


def test_issue294_historical_runner_prefers_host_supplied_source_commit(monkeypatch) -> None:
    expected = "7" * 40
    monkeypatch.setenv(historical_runner.SOURCE_COMMIT_ENV, expected)

    assert historical_runner.host_supplied_source_commit() == expected
