#!/usr/bin/env python3
"""Run the legacy evaluator after adapting HOMR's download_weights API.

This is temporary Issue #245 investigation tooling. It does not alter the
production HybridDetector route or monkeypatch any process other than this
standalone evaluator invocation.
"""

from __future__ import annotations

import sys
from typing import Any


def install_download_weights_compat(evaluator: Any) -> bool:
    """Adapt evaluator's zero-argument call to current HOMR's bool argument."""
    torch_module = getattr(evaluator, "torch", None)
    use_gpu_inference = bool(
        torch_module is not None and torch_module.cuda.is_available()
    )
    original_download_weights = evaluator.download_weights

    def download_weights_compat() -> None:
        original_download_weights(use_gpu_inference)

    evaluator.download_weights = download_weights_compat
    return use_gpu_inference


def main() -> int:
    from src.homr_eval_scripts import homr_evaluator

    use_gpu_inference = install_download_weights_compat(homr_evaluator)
    print(
        "Issue #245 evaluator compatibility shim: "
        f"use_gpu_inference={use_gpu_inference}"
    )
    homr_evaluator.run_evaluation(sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
