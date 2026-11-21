"""RapidOCR provider selection helpers for MMR OCR."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger(__name__)

RAPIDOCR_PROVIDER_AUTO = "auto"
RAPIDOCR_PROVIDER_CPU = "cpu"
RAPIDOCR_PROVIDER_CUDA = "cuda"
RAPIDOCR_PROVIDER_MODES = {
    RAPIDOCR_PROVIDER_AUTO,
    RAPIDOCR_PROVIDER_CPU,
    RAPIDOCR_PROVIDER_CUDA,
}

_BASIC_PROVIDER_INSPECTION_TYPES = (str, int, float, bytes, list, dict, set, tuple)


def normalize_rapidocr_provider(provider: str) -> str:
    provider_mode = str(provider or RAPIDOCR_PROVIDER_AUTO).strip().lower()
    if provider_mode not in RAPIDOCR_PROVIDER_MODES:
        raise ValueError(
            f"Unsupported MMR RapidOCR provider mode: {provider!r}. "
            f"Expected one of: {', '.join(sorted(RAPIDOCR_PROVIDER_MODES))}"
        )
    return provider_mode


def onnxruntime_has_cuda_provider() -> bool:
    try:
        import onnxruntime as ort

        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception as exc:
        logger.debug("Unable to inspect ONNX Runtime providers for MMR RapidOCR: %s", exc)
        return False


def _get_providers_from_obj(obj: Any, visited: Optional[set[int]] = None) -> Optional[List[str]]:
    if obj is None or isinstance(obj, _BASIC_PROVIDER_INSPECTION_TYPES):
        return None
    if visited is None:
        visited = set()
    obj_id = id(obj)
    if obj_id in visited:
        return None
    visited.add(obj_id)

    get_providers = getattr(obj, "get_providers", None)
    if callable(get_providers):
        try:
            return list(get_providers())
        except Exception as exc:
            logger.debug("Unable to inspect RapidOCR providers: %s", exc)
            return None
    # rapidocr_onnxruntime keeps the det/cls ONNX sessions under ``infer``
    # (OrtInferSession.session); without it only recognition was ever inspected.
    for attr_name in ("session", "sess", "net", "model", "infer"):
        nested = getattr(obj, attr_name, None)
        if nested is obj:
            continue
        providers = _get_providers_from_obj(nested, visited)
        if providers is not None:
            return providers
    return None


def collect_rapidocr_providers(ocr_engine: Any) -> Dict[str, List[str]]:
    providers: Dict[str, List[str]] = {}
    direct_providers = _get_providers_from_obj(ocr_engine)
    if direct_providers is not None:
        providers["engine"] = direct_providers

    for name in (
        "text_det",
        "det",
        "det_model",
        "text_cls",
        "cls",
        "cls_model",
        "text_rec",
        "rec",
        "rec_model",
    ):
        component = getattr(ocr_engine, name, None)
        component_providers = _get_providers_from_obj(component)
        if component_providers is not None:
            providers[name] = component_providers

    try:
        items = vars(ocr_engine).items()
    except TypeError:
        items = []
    for name, component in items:
        if name in providers or name.startswith("_"):
            continue
        component_providers = _get_providers_from_obj(component)
        if component_providers is not None:
            providers[name] = component_providers
    return providers


def providers_include_cuda(providers: Dict[str, List[str]]) -> bool:
    return any("CUDAExecutionProvider" in provider_list for provider_list in providers.values())


# The text detection, direction classification and recognition sessions MMR uses.
RAPIDOCR_COMPONENTS = ("text_det", "text_cls", "text_rec")


def providers_all_cuda(ocr_engine: Any, providers: Dict[str, List[str]]) -> bool:
    """True only if every OCR component present on the engine has a CUDA session.

    ``providers_include_cuda`` accepts a single CUDA session, so CUDA detection with
    CPU-only recognition would pass; the strict (fail-closed) check needs all of them.
    """

    expected = [name for name in RAPIDOCR_COMPONENTS if getattr(ocr_engine, name, None)]
    if not expected or not providers:
        return False
    if any(name not in providers for name in expected):
        return False
    return all("CUDAExecutionProvider" in provider_list for provider_list in providers.values())


REQUIRE_CUDA_ORT_ENV = "PDFSCORE_REQUIRE_CUDA_ORT"


def require_cuda_ort() -> bool:
    """Fail closed instead of warning on a CPU fallback (set by the Windows launcher)."""
    return os.environ.get(REQUIRE_CUDA_ORT_ENV) == "1"


def create_mmr_rapidocr(provider: str = RAPIDOCR_PROVIDER_AUTO) -> RapidOCR:
    provider_mode = normalize_rapidocr_provider(provider)
    if provider_mode == RAPIDOCR_PROVIDER_CPU:
        logger.info("Initializing MMR RapidOCR with CPU/default provider mode.")
        return RapidOCR()

    strict = require_cuda_ort()
    should_use_cuda = (
        provider_mode == RAPIDOCR_PROVIDER_CUDA or strict or onnxruntime_has_cuda_provider()
    )
    if not should_use_cuda:
        logger.info(
            "Initializing MMR RapidOCR with CPU/default provider mode; CUDA provider is unavailable."
        )
        return RapidOCR()

    logger.info("Initializing MMR RapidOCR with CUDA provider preference (mode=%s).", provider_mode)
    ocr_engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
    providers = collect_rapidocr_providers(ocr_engine)
    if strict and not providers_all_cuda(ocr_engine, providers):
        expected = [name for name in RAPIDOCR_COMPONENTS if getattr(ocr_engine, name, None)]
        raise RuntimeError(
            "MMR RapidOCR requested CUDA but not every OCR session is on "
            f"CUDAExecutionProvider ({REQUIRE_CUDA_ORT_ENV}=1); expected={expected}, "
            f"providers={providers or '<unavailable>'}"
        )
    if providers_include_cuda(providers):
        logger.info("MMR RapidOCR providers: %s", providers)
    else:
        logger.warning(
            "MMR RapidOCR CUDA provider was requested but CUDAExecutionProvider was not confirmed; "
            "providers=%s. Continuing with available fallback providers.",
            providers or "<unavailable>",
        )
    return ocr_engine
