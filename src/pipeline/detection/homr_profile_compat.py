#!/usr/bin/env python3
"""Run the pinned Stage E evaluator profile across compatible HOMR APIs.

The production detector uses this entrypoint only inside the isolated HOMR
profile runtime. It adapts API-shape drift between the pinned PDFScore
evaluator and pinned HOMR source without substituting detector artifacts.

The public helpers in this module are also the compatibility boundary for the
current HOMR worker. Callers pass the function/class object they actually hold,
so compatibility does not depend on patching ``homr.main`` after another
module has already bound a symbol with ``from homr.main import ...``.
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


def processing_config_compat_mode(processing_config_cls: type[Any]) -> str:
    signature = inspect.signature(processing_config_cls)
    if "use_gpu_inference" in signature.parameters:
        return "gpu_argument_injected_when_missing"
    return "native_without_gpu_argument"


def build_processing_config_compat(
    processing_config_cls: type[Any],
    *,
    enable_debug: bool,
    enable_cache: bool,
    write_staff_positions: bool,
    use_gpu_inference: bool,
) -> Any:
    """Construct ProcessingConfig across the known five/six-field HOMR APIs."""
    args = (
        enable_debug,
        enable_cache,
        write_staff_positions,
        False,
        -1,
    )
    mode = processing_config_compat_mode(processing_config_cls)
    if mode == "gpu_argument_injected_when_missing":
        return processing_config_cls(*args, use_gpu_inference)
    return processing_config_cls(*args)


def download_weights_compat_mode(download_weights: Any) -> str:
    signature = inspect.signature(download_weights)
    if "use_gpu_inference" in signature.parameters:
        return "gpu_argument_injected"
    required_arguments = _required_positional_count(download_weights)
    if required_arguments == 0:
        return "native_zero_argument"
    if required_arguments == 1:
        return "gpu_argument_injected"
    raise TypeError(f"Unsupported HOMR download_weights signature: {signature}")


def call_download_weights_compat(download_weights: Any, *, use_gpu_inference: bool) -> Any:
    """Call the bound download_weights symbol using its runtime signature."""
    mode = download_weights_compat_mode(download_weights)
    if mode == "native_zero_argument":
        return download_weights()
    return download_weights(use_gpu_inference)


def load_predictions_compat_mode(load_predictions: Any) -> str:
    signature = inspect.signature(load_predictions)
    if "use_gpu_inference" in signature.parameters:
        return "gpu_argument_injected_when_missing"
    if _required_positional_count(load_predictions) <= 3:
        return "native_without_gpu_argument"
    raise TypeError(f"Unsupported HOMR load_and_preprocess_predictions signature: {signature}")


def call_load_predictions_compat(
    load_predictions: Any,
    image_path: str,
    *,
    enable_debug: bool,
    enable_cache: bool,
    use_gpu_inference: bool,
) -> Any:
    """Call the bound preprocessing symbol across the known three/four-argument APIs."""
    mode = load_predictions_compat_mode(load_predictions)
    if mode == "gpu_argument_injected_when_missing":
        return load_predictions(image_path, enable_debug, enable_cache, use_gpu_inference)
    return load_predictions(image_path, enable_debug, enable_cache)


def parse_staffs_compat_mode(parse_staffs: Any) -> str:
    signature = inspect.signature(parse_staffs)
    if "config" in signature.parameters:
        return "transformer_config_injected_when_missing"
    return "native_without_config_argument"


def call_parse_staffs_compat(
    parse_staffs: Any,
    debug: Any,
    multi_staffs: Any,
    image: Any,
    *,
    selected_staff: int,
    use_gpu_inference: bool,
) -> Any:
    """Call the bound parse_staffs symbol without TypeError-based fallbacks."""
    mode = parse_staffs_compat_mode(parse_staffs)
    if mode == "native_without_config_argument":
        return parse_staffs(debug, multi_staffs, image, selected_staff=selected_staff)

    configs_module = importlib.import_module("homr.transformer.configs")
    transformer_config = configs_module.Config()
    if hasattr(transformer_config, "use_gpu_inference"):
        transformer_config.use_gpu_inference = use_gpu_inference
    return parse_staffs(
        debug,
        multi_staffs,
        image,
        config=transformer_config,
        selected_staff=selected_staff,
    )


def _install_processing_config_compat(evaluator: Any, *, use_gpu_inference: bool) -> str:
    original = evaluator.ProcessingConfig
    mode = processing_config_compat_mode(original)
    if mode == "native_without_gpu_argument":
        return mode
    signature = inspect.signature(original)

    def processing_config_compat(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
        return original(*args, **kwargs)

    evaluator.ProcessingConfig = processing_config_compat
    return mode


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
        if "use_gpu_inference" not in bound.arguments:
            kwargs["use_gpu_inference"] = use_gpu_inference
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
    if download_mode == "gpu_argument_injected":

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
