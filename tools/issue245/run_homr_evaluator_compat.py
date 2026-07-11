#!/usr/bin/env python3
"""Run the legacy evaluator across historical and current HOMR APIs.

This is temporary Issue #245 investigation tooling. It does not alter the
production HybridDetector route or monkeypatch any process other than this
standalone evaluator invocation.
"""

from __future__ import annotations

import inspect
import sys
from typing import Any


def _required_positional_count(callable_obj: Any) -> int:
    signature = inspect.signature(callable_obj)
    return sum(
        1
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and parameter.default is inspect.Parameter.empty
    )


def install_homr_api_compat(evaluator: Any) -> bool:
    """Adapt evaluator calls to either historical or current HOMR APIs."""
    torch_module = getattr(evaluator, "torch", None)
    use_gpu_inference = bool(
        torch_module is not None and torch_module.cuda.is_available()
    )

    original_download_weights = evaluator.download_weights
    required_arguments = _required_positional_count(original_download_weights)
    if required_arguments == 1:

        def download_weights_compat() -> None:
            original_download_weights(use_gpu_inference)

        evaluator.download_weights = download_weights_compat
        download_mode = "gpu_argument_injected"
    elif required_arguments == 0:
        download_mode = "native_zero_argument"
    else:
        raise TypeError(
            "Unsupported HOMR download_weights signature: "
            f"{inspect.signature(original_download_weights)}"
        )

    processing_config = evaluator.ProcessingConfig
    annotations = getattr(processing_config, "__annotations__", {})
    if "use_gpu_inference" in annotations and not hasattr(
        processing_config, "use_gpu_inference"
    ):
        # The evaluator uses hasattr() on the dataclass type. Required dataclass
        # fields without defaults exist only in __annotations__, so expose a
        # class marker that selects the six-argument construction path.
        setattr(processing_config, "use_gpu_inference", None)

    evaluator._issue245_download_weights_mode = download_mode
    return use_gpu_inference


def main() -> int:
    from src.homr_eval_scripts import homr_evaluator

    use_gpu_inference = install_homr_api_compat(homr_evaluator)
    print(
        "Issue #245 evaluator compatibility shim: "
        f"use_gpu_inference={use_gpu_inference} "
        f"download_weights_mode={homr_evaluator._issue245_download_weights_mode}"
    )
    homr_evaluator.run_evaluation(sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
