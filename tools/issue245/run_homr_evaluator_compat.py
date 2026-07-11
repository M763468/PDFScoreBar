#!/usr/bin/env python3
"""Run the legacy evaluator after adapting current HOMR API changes.

This is temporary Issue #245 investigation tooling. It does not alter the
production HybridDetector route or monkeypatch any process other than this
standalone evaluator invocation.
"""

from __future__ import annotations

import sys
from typing import Any


def install_homr_api_compat(evaluator: Any) -> bool:
    """Adapt legacy evaluator calls to current HOMR's GPU-aware API."""
    torch_module = getattr(evaluator, "torch", None)
    use_gpu_inference = bool(
        torch_module is not None and torch_module.cuda.is_available()
    )

    original_download_weights = evaluator.download_weights

    def download_weights_compat() -> None:
        original_download_weights(use_gpu_inference)

    evaluator.download_weights = download_weights_compat

    processing_config = evaluator.ProcessingConfig
    annotations = getattr(processing_config, "__annotations__", {})
    if "use_gpu_inference" in annotations and not hasattr(
        processing_config, "use_gpu_inference"
    ):
        # The legacy evaluator uses hasattr() on the dataclass type. Required
        # dataclass fields without defaults exist in __annotations__ but are not
        # class attributes, so expose a marker that selects the six-argument path.
        setattr(processing_config, "use_gpu_inference", None)

    return use_gpu_inference


def main() -> int:
    from src.homr_eval_scripts import homr_evaluator

    use_gpu_inference = install_homr_api_compat(homr_evaluator)
    print(
        "Issue #245 evaluator compatibility shim: "
        f"use_gpu_inference={use_gpu_inference}"
    )
    homr_evaluator.run_evaluation(sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
