"""Opt-in deep attribution wrappers for the current-runtime HOMR worker.

The wrappers are installed only while ``PDFSCORE_PERF_TRACE_DIR`` is enabled.
They intentionally wrap the final consumer bindings after compatibility shims are
installed, so disabled production execution is completely unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from types import ModuleType
from typing import Any

from src.pipeline.perf_trace import enabled, span

_WRAPPED_MARKER = "__pdfscore_current_homr_perf_wrapped__"


def _wrap_callable(module: ModuleType, name: str, stage: str, *, cuda: bool = False) -> bool:
    target = getattr(module, name, None)
    if target is None or not callable(target):
        return False
    if getattr(target, _WRAPPED_MARKER, False):
        return False

    original: Callable[..., Any] = target

    @wraps(original)
    def measured(*args: Any, **kwargs: Any) -> Any:
        with span(stage, cuda=cuda):
            return original(*args, **kwargs)

    setattr(measured, _WRAPPED_MARKER, True)
    setattr(module, name, measured)
    return True


def install_current_homr_perf_attribution(
    homr_main: ModuleType,
    homr_predictor: ModuleType,
    homr_heuristics: ModuleType,
) -> list[str]:
    """Wrap current-HOMR subphases and return the installed stage names.

    CUDA synchronization is used only for the two neural-heavy boundaries whose
    durations need to be distinguished causally: segmentation/preprocessing and
    transformer staff parsing. All other wrappers are ordinary wall/CPU spans.
    """
    if not enabled():
        return []

    specs: tuple[tuple[ModuleType, str, str, bool], ...] = (
        (
            homr_predictor,
            "run_homr_on_image",
            "current_homr.core.run_homr_on_image_total",
            False,
        ),
        (
            homr_predictor,
            "detect_staffs_with_barlines",
            "current_homr.core.detect_staffs_with_barlines_total",
            False,
        ),
        (
            homr_heuristics,
            "load_and_preprocess_predictions",
            "current_homr.core.segnet_load_preprocess",
            True,
        ),
        (
            homr_heuristics,
            "predict_symbols",
            "current_homr.core.symbol_postprocess",
            False,
        ),
        (
            homr_heuristics,
            "break_wide_fragments",
            "current_homr.core.break_wide_fragments",
            False,
        ),
        (
            homr_heuristics,
            "combine_noteheads_with_stems",
            "current_homr.core.combine_noteheads_stems",
            False,
        ),
        (
            homr_heuristics,
            "detect_staff",
            "current_homr.core.staff_detection",
            False,
        ),
        (
            homr_heuristics,
            "prepare_brace_dot_image",
            "current_homr.core.brace_dot_prepare",
            False,
        ),
        (
            homr_heuristics,
            "add_notes_to_staffs",
            "current_homr.core.add_notes_to_staffs",
            False,
        ),
        (
            homr_heuristics,
            "find_braces_brackets_and_grand_staff_lines",
            "current_homr.core.staff_grouping",
            False,
        ),
        (
            homr_main,
            "parse_staffs",
            "current_homr.core.transformer_parse_staffs",
            True,
        ),
        (
            homr_predictor,
            "generate_xml",
            "current_homr.core.generate_xml",
            False,
        ),
        (
            homr_predictor,
            "compute_transform_info",
            "current_homr.post.map_transform",
            False,
        ),
        (
            homr_predictor,
            "detect_thin_vertical_runs",
            "current_homr.post.thin_barline_detection",
            False,
        ),
        (
            homr_predictor,
            "filter_detections_by_notehead_proximity",
            "current_homr.post.heuristic_rejection",
            False,
        ),
        (
            homr_predictor,
            "recover_end_barlines",
            "current_homr.post.end_barline_recovery",
            False,
        ),
    )

    installed: list[str] = []
    for module, name, stage, cuda in specs:
        if _wrap_callable(module, name, stage, cuda=cuda):
            installed.append(stage)
    return installed
