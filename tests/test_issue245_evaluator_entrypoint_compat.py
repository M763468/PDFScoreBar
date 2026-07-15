from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tools.issue245 import run_homr_evaluator_compat as compat


def test_prefers_run_evaluation_entrypoint() -> None:
    calls: list[list[str]] = []
    evaluator = SimpleNamespace(
        run_evaluation=lambda argv: calls.append(list(argv)),
        main=lambda: pytest.fail("main() must not be selected"),
    )

    mode = compat._entrypoint_mode(evaluator)
    compat._run_evaluator_entrypoint(
        evaluator,
        ["--images", "page.png"],
        entrypoint_mode=mode,
    )

    assert mode == "run_evaluation_argv"
    assert calls == [["--images", "page.png"]]


def test_falls_back_to_main_with_temporary_sys_argv() -> None:
    original_argv = list(sys.argv)
    captured: list[list[str]] = []

    def historical_main() -> None:
        captured.append(list(sys.argv))

    evaluator = SimpleNamespace(main=historical_main)
    mode = compat._entrypoint_mode(evaluator)
    compat._run_evaluator_entrypoint(
        evaluator,
        ["--images", "page.png"],
        entrypoint_mode=mode,
    )

    assert mode == "main_sys_argv"
    assert captured == [[original_argv[0], "--images", "page.png"]]
    assert sys.argv == original_argv


def test_removes_cache_flag_only_when_cache_module_is_unavailable() -> None:
    evaluator = SimpleNamespace(_issue245_segnet_cache_mode="not_available")

    argv, mode = compat._prepare_evaluator_argv(
        evaluator,
        ["--images", "page.png", "--enable-segnet-cache"],
    )

    assert argv == ["--images", "page.png"]
    assert mode == "removed_unavailable_segnet_cache_flag"


def test_preserves_cache_flag_for_supported_evaluator() -> None:
    evaluator = SimpleNamespace(
        _issue245_segnet_cache_mode="native_one_or_two_argument_constructor"
    )
    original = ["--images", "page.png", "--enable-segnet-cache"]

    argv, mode = compat._prepare_evaluator_argv(evaluator, original)

    assert argv == original
    assert mode == "unchanged"


def test_rejects_evaluator_without_cli_entrypoint() -> None:
    with pytest.raises(AttributeError, match="neither run_evaluation"):
        compat._entrypoint_mode(SimpleNamespace())
