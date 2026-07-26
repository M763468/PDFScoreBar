"""Capture HOMR connector semantics without enabling the full debug output surface."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

import numpy as np

from src.common.connector_artifacts import write_connector_masks

logger = logging.getLogger(__name__)
_CAPTURE_LOCK = RLock()
_PATCH_MARKER = "_pdfscore_connector_artifact_capture"


def install_homr_connector_artifact_capture(predictor_cls: type[Any] | None = None) -> bool:
    """Wrap ``HomrPredictor.predict`` so semantic connector masks survive production runs."""

    if predictor_cls is None:
        try:
            from src.homr_eval_scripts.core.predictor import HomrPredictor
        except ImportError:
            return False
        predictor_cls = HomrPredictor

    original_predict = predictor_cls.predict
    if getattr(original_predict, _PATCH_MARKER, False):
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

    setattr(predict_with_connector_artifacts, _PATCH_MARKER, True)
    predictor_cls.predict = predict_with_connector_artifacts
    return True


@contextmanager
def capture_homr_threshold_masks(debug_cls: type[Any] | None = None) -> Iterator[dict[str, np.ndarray]]:
    """Capture ``symbols`` and ``brace_dot`` masks emitted by HOMR's Debug boundary."""

    if debug_cls is None:
        try:
            from homr.debug import Debug
        except ImportError:
            yield {}
            return
        debug_cls = Debug

    captured: dict[str, np.ndarray] = {}
    with _CAPTURE_LOCK:
        original_write = debug_cls.write_threshold_image

        def write_and_capture(self: Any, suffix: str, image: np.ndarray) -> Any:
            if suffix in {"symbols", "brace_dot"}:
                captured[suffix] = np.array(image, copy=True)
            return original_write(self, suffix, image)

        debug_cls.write_threshold_image = write_and_capture
        try:
            yield captured
        finally:
            debug_cls.write_threshold_image = original_write
