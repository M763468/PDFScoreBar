from __future__ import annotations

from tools.issue294.run_full68_refresh_experiment import _exit_code


def test_interactive_default_never_propagates_experiment_failure() -> None:
    assert _exit_code("failed", strict_exit=False) == 0
    assert _exit_code("completed", strict_exit=False) == 0


def test_strict_exit_is_opt_in() -> None:
    assert _exit_code("failed", strict_exit=True) == 1
    assert _exit_code("completed", strict_exit=True) == 0
