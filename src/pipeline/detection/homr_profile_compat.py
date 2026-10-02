#!/usr/bin/env python3
"""Run the pinned historical Stage-E evaluator across compatible HOMR APIs.

Maintained/current workers use ``src.homr_runtime.api_compat`` directly. This
entrypoint retains historical evaluator adaptation and re-exports the shared
callable helpers for old consumers; it is outside the minimal runtime bundle.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any

from src.homr_runtime.api_compat import (
    _original_consumer_callable as _original_consumer_callable,
)
from src.homr_runtime.api_compat import (
    _required_positional_count as _required_positional_count,
)
from src.homr_runtime.api_compat import (
    build_processing_config_compat as build_processing_config_compat,
)
from src.homr_runtime.api_compat import (
    call_download_weights_compat as call_download_weights_compat,
)
from src.homr_runtime.api_compat import (
    call_load_predictions_compat as call_load_predictions_compat,
)
from src.homr_runtime.api_compat import (
    call_parse_staffs_compat as call_parse_staffs_compat,
)
from src.homr_runtime.api_compat import (
    download_weights_compat_mode as download_weights_compat_mode,
)
from src.homr_runtime.api_compat import (
    install_current_homr_consumer_compat as install_current_homr_consumer_compat,
)
from src.homr_runtime.api_compat import (
    load_predictions_compat_mode as load_predictions_compat_mode,
)
from src.homr_runtime.api_compat import (
    parse_staffs_compat_mode as parse_staffs_compat_mode,
)
from src.homr_runtime.api_compat import (
    processing_config_compat_mode as processing_config_compat_mode,
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
    mode = processing_config_compat_mode(original)
    if mode == "native_without_gpu_argument":
        return mode
    signature = inspect.signature(original)

    def processing_config_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        if mode == "gpu_argument_injected_when_missing":
            if "use_gpu_inference" not in bound.arguments:
                kwargs["use_gpu_inference"] = use_gpu_inference
        elif mode == "split_gpu_arguments_injected_when_missing":
            if "transformer_use_gpu" not in bound.arguments:
                kwargs["transformer_use_gpu"] = use_gpu_inference
            if "segnet_use_gpu" not in bound.arguments:
                kwargs["segnet_use_gpu"] = use_gpu_inference
        else:
            return original(*args, **kwargs)
        return original(*args, **kwargs)

    evaluator.ProcessingConfig = processing_config_compat
    return mode


def _inject_gpu_keyword_for_signature(
    signature: inspect.Signature,
    kwargs: dict[str, Any],
    bound: inspect.BoundArguments,
    *,
    use_gpu_inference: bool,
) -> None:
    if "use_gpu_inference" in signature.parameters:
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
        return
    for name in ("transformer_use_gpu", "segnet_use_gpu"):
        if name in signature.parameters and name not in bound.arguments:
            kwargs[name] = use_gpu_inference


def _install_load_predictions_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = getattr(evaluator, "load_and_preprocess_predictions", None)
    if original is None:
        return "not_exported"
    mode = load_predictions_compat_mode(original)
    if mode == "native_without_gpu_argument":
        return mode
    signature = inspect.signature(original)

    def load_predictions_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        _inject_gpu_keyword_for_signature(
            signature,
            kwargs,
            bound,
            use_gpu_inference=use_gpu_inference,
        )
        return original(*args, **kwargs)

    evaluator.load_and_preprocess_predictions = load_predictions_compat
    return mode


def _install_parse_staffs_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = getattr(evaluator, "parse_staffs", None)
    if original is None:
        return "not_exported"
    mode = parse_staffs_compat_mode(original)
    if mode == "native_without_config_argument":
        return mode
    signature = inspect.signature(original)
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
    return mode


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
    download_mode = download_weights_compat_mode(original_download_weights)
    if download_mode in {"gpu_argument_injected", "split_gpu_arguments"}:

        def download_weights_compat() -> None:
            call_download_weights_compat(
                original_download_weights,
                use_gpu_inference=use_gpu_inference,
            )

        evaluator.download_weights = download_weights_compat

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


def _prepare_evaluator_argv(
    evaluator: Any, argv: list[str], *, segnet_cache_mode: str
) -> list[str]:
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
