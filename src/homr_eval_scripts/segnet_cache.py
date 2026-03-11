"""Segnet cache patcher to avoid repeated ONNXRuntime model loads."""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, Tuple

import onnxruntime as ort

logger = logging.getLogger(__name__)

_SEGNET_CACHE_LOCK = threading.Lock()
_SEGNET_SESSION_CACHE: Dict[Tuple[str, bool], ort.InferenceSession] = {}


def _create_session(model_path: str, use_gpu: bool) -> ort.InferenceSession:
    if use_gpu:
        try:
            session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
        except Exception as exc:
            logger.debug(
                "Error while trying to load model using CUDA. You probably don't have a compatible gpu"
            )
            logger.debug(exc)
            session = ort.InferenceSession(model_path)
    else:
        session = ort.InferenceSession(model_path)

    if (
        os.environ.get("HOMR_DEBUG_PROVIDERS") == "1"
        and ort.get_available_providers()
        and session.get_providers()
    ):
        logger.debug(
            "Segnet ORT providers (available/selected): "
            f"{ort.get_available_providers()} / {session.get_providers()}"
        )

    return session


def _get_session(model_path: str, use_gpu: bool) -> ort.InferenceSession:
    key = (model_path, use_gpu)
    with _SEGNET_CACHE_LOCK:
        if key in _SEGNET_SESSION_CACHE:
            return _SEGNET_SESSION_CACHE[key]
        logger.debug(f"Segnet cache: creating session for {model_path} (gpu={use_gpu})")
        session = _create_session(model_path, use_gpu)
        _SEGNET_SESSION_CACHE[key] = session
        return session


class CachedSegnet:
    """Drop-in replacement for homr.segmentation.inference_segnet.Segnet."""

    def __init__(self, model_path: str, use_gpu: bool) -> None:
        self.model = _get_session(model_path, use_gpu)
        self.input_name = self.model.get_inputs()[0].name
        self.output_name = self.model.get_outputs()[0].name

    def run(self, input_data):
        return self.model.run([self.output_name], {self.input_name: input_data})[0]


def clear_segnet_cache() -> None:
    """Clear the Segnet session cache and release VRAM/RAM."""
    global _SEGNET_SESSION_CACHE
    with _SEGNET_CACHE_LOCK:
        for session in _SEGNET_SESSION_CACHE.values():
            # session is onnxruntime.InferenceSession.
            # While it doesn't have an explicit close() in all versions,
            # deleting it helps release references.
            del session
        _SEGNET_SESSION_CACHE.clear()
    logger.debug("Segnet cache cleared.")


def enable_segnet_cache() -> bool:
    """Patch homr.segmentation.inference_segnet.Segnet with a cached variant."""
    import homr.segmentation.inference_segnet as target

    if getattr(target, "_SEGNET_CACHE_ENABLED", False):
        return False

    target.Segnet = CachedSegnet  # type: ignore[attr-defined]
    target._SEGNET_CACHE_ENABLED = True
    return True
