#!/usr/bin/env python3
"""Run the pinned Stage E evaluator profile across compatible HOMR APIs.

The production detector uses this entrypoint only inside the isolated HOMR
profile runtime.  It adapts API-shape drift between the pinned PDFScore
evaluator and pinned HOMR source without substituting detector artifacts.
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
    torch_module = getattr(evaluator, "torch", None)
    if torch_module is None:
        try:
            torch_module = importlib.import_module("torch")
        except ImportError:
            return False
    cuda_module = getattr(torch_module, "cuda", None)
    return bool(cuda_module is not None and cuda_module.is_available())


def _install_processing_config_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = evaluator.ProcessingConfig
    signature = inspect.signature(original)
    if "use_gpu_inference" not in signature.parameters:
        return "native_without_gpu_argument"

    def processing_config_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
        return original(*args, **kwargs)

    evaluator.ProcessingConfig = processing_config_compat
    return "gpu_argument_injected_when_missing"


def _install_load_predictions_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = getattr(evaluator, "load_and_preprocess_predictions", None)
    if original is None:
        return "not_exported"
    signature = inspect.signature(original)
    if "use_gpu_inference" not in signature.parameters:
        return "native_without_gpu_argument"

    def load_predictions_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
        return original(*args, **kwargs)

    evaluator.load_and_preprocess_predictions = load_predictions_compat
    return "gpu_argument_injected_when_missing"


def _install_parse_staffs_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = getattr(evaluator, "parse_staffs", None)
    if original is None:
        return "not_exported"
    signature = inspect.signature(original)
    if "config" not in signature.parameters:
        return "native_without_config_argument"

    transformer_config: Any | None = None

    def parse_staffs_compat(*args: Any, **kwargs: Any) -> Any:
        nonlocal transformer_config
        bound = signature.bind_partial(*args, **kwargs)
        if "config" not in bound.arguments:
            if transformer_config is None:
                configs_module = importlib.import_module("homr.transformer.configs")
                transformer_config = configs_module.Config()
                if hasattr(transformer_config, "use_gpu_inference"):
                    transformer_config.use_gpu_inference = use_gpu_inference
            kwargs["config"] = transformer_config
        return original(*args, **kwargs)

    evaluator.parse_staffs = parse_staffs_compat
    return "transformer_config_injected_when_missing"


def _install_segnet_cache_compat() -> str:
    try:
        cache_module = importlib.import_module("homr_eval_scripts.segnet_cache")
    except ImportError:
        return "not_available"

    cached_segnet = getattr(cache_module, "CachedSegnet", None)
    get_session = getattr(cache_module, "_get_session", None)
    if cached_segnet is None or get_session is None:
        return "unsupported_module"
    if _required_positional_count(cached_segnet) <= 1:
        return "native_one_or_two_argument_constructor"

    class CachedSegnetCompat:
        def __init__(self, model_path_or_use_gpu: str | bool, use_gpu: bool | None = None) -> None:
            if use_gpu is None:
                config_module = importlib.import_module("homr.segmentation.config")
                gpu_enabled = bool(model_path_or_use_gpu)
                fp32_path = config_module.segnet_path_onnx
                fp16_path = getattr(config_module, "segnet_path_onnx_fp16", fp32_path)
                model_path = fp16_path if gpu_enabled else fp32_path
            else:
                model_path = str(model_path_or_use_gpu)
                gpu_enabled = bool(use_gpu)
            self.model = get_session(model_path, gpu_enabled)
            self.input_name = self.model.get_inputs()[0].name
            self.output_name = self.model.get_outputs()[0].name

        def run(self, input_data: Any) -> Any:
            if self.model.get_inputs()[0].type == "tensor(float16)":
                numpy_module = importlib.import_module("numpy")
                input_data = input_data.astype(numpy_module.float16)
            return self.model.run([self.output_name], {self.input_name: input_data})[0]

    cache_module.CachedSegnet = CachedSegnetCompat
    return "one_or_two_argument_constructor_injected"


def install_homr_api_compat(evaluator: Any) -> dict[str, Any]:
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

    return {
        "use_gpu_inference": use_gpu_inference,
        "download_weights_mode": download_mode,
        "processing_config_mode": _install_processing_config_compat(
            evaluator, use_gpu_inference=use_gpu_inference
        ),
        "load_predictions_mode": _install_load_predictions_compat(
            evaluator, use_gpu_inference=use_gpu_inference
        ),
        "parse_staffs_mode": _install_parse_staffs_compat(
            evaluator, use_gpu_inference=use_gpu_inference
        ),
        "segnet_cache_mode": _install_segnet_cache_compat(),
    }


def _prepare_evaluator_argv(evaluator: Any, argv: list[str], *, segnet_cache_mode: str) -> list[str]:
    prepared = list(argv)
    if segnet_cache_mode == "not_available":
        while "--enable-segnet-cache" in prepared:
            prepared.remove("--enable-segnet-cache")
    return prepared


def _run_entrypoint(evaluator: Any, argv: list[str]) -> None:
    run_evaluation = getattr(evaluator, "run_evaluation", None)
    if callable(run_evaluation):
        run_evaluation(argv)
        return

    main = getattr(evaluator, "main", None)
    if not callable(main):
        raise AttributeError("Evaluator exports neither run_evaluation() nor main()")
    original_argv = sys.argv
    sys.argv = [original_argv[0], *argv]
    try:
        result = main()
    finally:
        sys.argv = original_argv
    if isinstance(result, int) and result != 0:
        raise SystemExit(result)


def main() -> int:
    from src.homr_eval_scripts import homr_evaluator

    modes = install_homr_api_compat(homr_evaluator)
    argv = _prepare_evaluator_argv(
        homr_evaluator,
        sys.argv[1:],
        segnet_cache_mode=str(modes["segnet_cache_mode"]),
    )
    _run_entrypoint(homr_evaluator, argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
