"""RapidOCR provider selection helpers for MMR OCR."""

from __future__ import annotations

import logging
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


def _get_providers_from_obj(obj: Any) -> Optional[List[str]]:
    if obj is None:
        return None
    get_providers = getattr(obj, "get_providers", None)
    if callable(get_providers):
        try:
            return list(get_providers())
        except Exception as exc:
            logger.debug("Unable to inspect RapidOCR providers: %s", exc)
            return None
    for attr_name in ("session", "sess", "net", "model"):
        nested = getattr(obj, attr_name, None)
        if nested is obj:
            continue
        providers = _get_providers_from_obj(nested)
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


def create_mmr_rapidocr(provider: str = RAPIDOCR_PROVIDER_AUTO) -> RapidOCR:
    provider_mode = normalize_rapidocr_provider(provider)
    if provider_mode == RAPIDOCR_PROVIDER_CPU:
        logger.info("Initializing MMR RapidOCR with CPU/default provider mode.")
        return RapidOCR()

    should_use_cuda = provider_mode == RAPIDOCR_PROVIDER_CUDA or onnxruntime_has_cuda_provider()
    if not should_use_cuda:
        logger.info("Initializing MMR RapidOCR with CPU/default provider mode; CUDA provider is unavailable.")
        return RapidOCR()

    logger.info("Initializing MMR RapidOCR with CUDA provider preference (mode=%s).", provider_mode)
    ocr_engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
    providers = collect_rapidocr_providers(ocr_engine)
    if providers_include_cuda(providers):
        logger.info("MMR RapidOCR providers: %s", providers)
    else:
        logger.warning(
            "MMR RapidOCR CUDA provider was requested but CUDAExecutionProvider was not confirmed; "
            "providers=%s. Continuing with available fallback providers.",
            providers or "<unavailable>",
        )
    return ocr_engine
