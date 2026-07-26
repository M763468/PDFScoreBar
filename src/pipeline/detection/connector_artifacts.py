"""Capture HOMR connector semantics without enabling the full debug output surface."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Iterator

import numpy as np

from src.common.connector_artifacts import write_connector_masks

logger = logging.getLogger(__name__)
_CAPTURE_CONTEXT: ContextVar[dict[str, np.ndarray] | None] = ContextVar(
    "pdfscore_connector_artifact_capture",
    default=None,
)
_HOOK_LOCK = Lock()
_PREDICT_PATCH_MARKER = "_pdfscore_connector_artifact_capture"
_DEBUG_PATCH_MARKER = "_pdfscore_connector_debug_capture"


def install_homr_connector_artifact_capture(predictor_cls: type[Any] | None = None) -> bool:
    """Wrap ``HomrPredictor.predict`` so semantic connector masks survive production runs."""

    if predictor_cls is None:
        try:
            from src.homr_eval_scripts.core.predictor import HomrPredictor
        except ImportError:
            return False
        predictor_cls = HomrPredictor

    original_predict = predictor_cls.predict
    if getattr(original_predict, _PREDICT_PATCH_MARKER, False):
        return True

    @wraps(original_predict)
    def predict_with_connector_artifacts(
        self: Any,
        image_path: Path,
        xml_args: Any,
        sr_scale: int = 1,
        timeout_s: float = 0.0,
        image_run_dir: Path | None = None,
    ) -> Any:
        with capture_homr_threshold_masks() as captured:
            result = original_predict(
                self,
                image_path,
                xml_args,
                sr_scale=sr_scale,
                timeout_s=timeout_s,
                image_run_dir=image_run_dir,
            )

        if image_run_dir is not None:
            paths = write_connector_masks(Path(image_run_dir), Path(image_path).stem, captured)
            if paths is None:
                logger.warning(
                    "HOMR did not expose both connector semantic masks for %s; "
                    "numbering will use its explicit page-image fallback.",
                    image_path,
                )
        return result

    setattr(predict_with_connector_artifacts, _PREDICT_PATCH_MARKER, True)
    predictor_cls.predict = predict_with_connector_artifacts
    return True


@contextmanager
def capture_homr_threshold_masks(
    debug_cls: type[Any] | None = None,
) -> Iterator[dict[str, np.ndarray]]:
    """Capture ``symbols`` and ``brace_dot`` masks emitted in the current execution context."""

    if debug_cls is None:
        try:
            from homr.debug import Debug
        except ImportError:
            yield {}
            return
        debug_cls = Debug

    _install_debug_capture_hook(debug_cls)
    captured: dict[str, np.ndarray] = {}
    token = _CAPTURE_CONTEXT.set(captured)
    try:
        yield captured
    finally:
        _CAPTURE_CONTEXT.reset(token)


def _install_debug_capture_hook(debug_cls: type[Any]) -> None:
    current_write = debug_cls.write_threshold_image
    if getattr(current_write, _DEBUG_PATCH_MARKER, False):
        return

    with _HOOK_LOCK:
        current_write = debug_cls.write_threshold_image
        if getattr(current_write, _DEBUG_PATCH_MARKER, False):
            return

        @wraps(current_write)
        def write_and_capture(self: Any, suffix: str, image: np.ndarray) -> Any:
            captured = _CAPTURE_CONTEXT.get()
            if captured is not None and suffix in {"symbols", "brace_dot"}:
                captured[suffix] = np.array(image, copy=True)
            return current_write(self, suffix, image)

        setattr(write_and_capture, _DEBUG_PATCH_MARKER, True)
        debug_cls.write_threshold_image = write_and_capture
