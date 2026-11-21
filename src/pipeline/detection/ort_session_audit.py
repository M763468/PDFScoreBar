"""Record the ONNX Runtime sessions a worker really creates (#535).

``onnxruntime.get_available_providers()`` lists CUDA even when the CUDA/cuDNN DLLs
cannot be loaded; the session then silently runs on CPU. Only the providers of each
created session show what actually runs, so GPU workers record every session and
fail closed when a CUDA-requesting session is not active on CUDA.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.pipeline.detection.maintained_homr_worker import (
    _serialize_requested_providers,
    _validate_cuda_session_records,
)

__all__ = ["install_session_recorder", "validate_cuda_sessions"]


def install_session_recorder(ort: Any) -> tuple[list[dict[str, Any]], Callable[[], None]]:
    """Patch ``ort.InferenceSession``; return the records and a restore callable."""

    records: list[dict[str, Any]] = []
    original = ort.InferenceSession

    def recorded_inference_session(path_or_bytes: Any, *args: Any, **kwargs: Any) -> Any:
        requested = kwargs.get("providers")
        if requested is None and len(args) >= 2:
            requested = args[1]
        serialized = _serialize_requested_providers(requested)
        model = path_or_bytes if isinstance(path_or_bytes, str) else "<bytes>"
        try:
            session = original(path_or_bytes, *args, **kwargs)
        except Exception as error:
            records.append(
                {
                    "model": str(model),
                    "requested_providers": serialized,
                    "active_providers": [],
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            raise
        records.append(
            {
                "model": str(model),
                "requested_providers": serialized,
                "active_providers": list(session.get_providers()),
            }
        )
        return session

    ort.InferenceSession = recorded_inference_session

    def restore() -> None:
        ort.InferenceSession = original

    return records, restore


def validate_cuda_sessions(
    records: list[dict[str, Any]], *, use_gpu_inference: bool, ort: Any
) -> None:
    _validate_cuda_session_records(
        records,
        use_gpu_inference=use_gpu_inference,
        available_providers=list(ort.get_available_providers()),
    )
