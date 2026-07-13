#!/usr/bin/env python3
"""Run the legacy evaluator across historical and current HOMR APIs.

This is temporary Issue #245 investigation tooling. It does not alter the
production HybridDetector route or monkeypatch any process other than this
standalone evaluator invocation.
"""

from __future__ import annotations

import importlib
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


def _gpu_available(evaluator: Any) -> bool:
    """Resolve CUDA availability even when a historical evaluator omits torch."""
    torch_module = getattr(evaluator, "torch", None)
    if torch_module is None:
        try:
            torch_module = importlib.import_module("torch")
        except ImportError:
            return False

    cuda_module = getattr(torch_module, "cuda", None)
    return bool(cuda_module is not None and cuda_module.is_available())


def _install_processing_config_compat(
    evaluator: Any, *, use_gpu_inference: bool
) -> str:
    """Inject a newly required HOMR config field into older evaluator calls."""
    original_processing_config = evaluator.ProcessingConfig
    signature = inspect.signature(original_processing_config)
    if "use_gpu_inference" not in signature.parameters:
        return "native_without_gpu_argument"

    def processing_config_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
        return original_processing_config(*args, **kwargs)

    evaluator.ProcessingConfig = processing_config_compat
    return "gpu_argument_injected_when_missing"


def install_homr_api_compat(evaluator: Any) -> bool:
    """Adapt evaluator calls to either historical or current HOMR APIs."""
    use_gpu_inference = _gpu_available(evaluator)

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

    processing_config_mode = _install_processing_config_compat(
        evaluator, use_gpu_inference=use_gpu_inference
    )

    evaluator._issue245_download_weights_mode = download_mode
    evaluator._issue245_processing_config_mode = processing_config_mode
    return use_gpu_inference


def main() -> int:
    from src.homr_eval_scripts import homr_evaluator

    use_gpu_inference = install_homr_api_compat(homr_evaluator)
    print(
        "Issue #245 evaluator compatibility shim: "
        f"use_gpu_inference={use_gpu_inference} "
        f"download_weights_mode={homr_evaluator._issue245_download_weights_mode} "
        "processing_config_mode="
        f"{homr_evaluator._issue245_processing_config_mode}"
    )
    homr_evaluator.run_evaluation(sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
