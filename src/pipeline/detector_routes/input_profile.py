"""Input normalization for the production dense detector profile.

The validated detector/MMR result depends on both the detector route and the
raster resolution used to create page images from a PDF.  Keep that input
contract next to the detector-route selection so config omissions cannot
silently fall back to the older 300 dpi path.
"""

from __future__ import annotations

from typing import Any

from src.pipeline.detector_routes.production_dense import resolve_detector_route

DENSE_PDF_RASTER_DPI = 360.0
_INPUT_PROFILE_KEY = "_dense_input_profile"


def normalize_dense_input_profile(config: dict[str, Any]) -> None:
    """Apply the dense profile's PDF raster contract before page rendering.

    External/pre-rendered images are not resampled here.  For PDF input, the
    production dense route owns the raster DPI and overwrites partial or stale
    source config values.  The original/effective values are retained until the
    detector manifest metadata is built.
    """

    detection = config.get("detection")
    if detection is None:
        detection = {}
        config["detection"] = detection
    if not isinstance(detection, dict):
        raise ValueError("detection must be a mapping when provided")

    route, _ = resolve_detector_route(detection)
    if route != "dense":
        detection.pop(_INPUT_PROFILE_KEY, None)
        return

    steps = config.get("steps") or {}
    if not isinstance(steps, dict):
        raise ValueError("steps must be a mapping when provided")

    pdf_enabled = bool(steps.get("pdf_to_images", False))
    if not pdf_enabled:
        detection.setdefault(
            _INPUT_PROFILE_KEY,
            {
                "source": "external_images",
                "managed": False,
                "reason": "Pre-rendered images keep their source resolution.",
            },
        )
        return

    inputs = config.get("inputs")
    if inputs is None:
        inputs = {}
        config["inputs"] = inputs
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a mapping when provided")

    pdf_options = inputs.get("pdf_to_images")
    if pdf_options is None:
        pdf_options = {}
        inputs["pdf_to_images"] = pdf_options
    if not isinstance(pdf_options, dict):
        raise ValueError("inputs.pdf_to_images must be a mapping when provided")

    configured_dpi = pdf_options.get("dpi")
    detection.setdefault(
        _INPUT_PROFILE_KEY,
        {
            "source": "pdf",
            "managed": True,
            "dpi": {
                "configured": configured_dpi,
                "effective": DENSE_PDF_RASTER_DPI,
            },
        },
    )
    pdf_options["dpi"] = DENSE_PDF_RASTER_DPI


def pop_dense_input_profile_metadata(det_cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Remove and return manifest metadata created during input normalization."""

    value = det_cfg.pop(_INPUT_PROFILE_KEY, None)
    return value if isinstance(value, dict) else None
