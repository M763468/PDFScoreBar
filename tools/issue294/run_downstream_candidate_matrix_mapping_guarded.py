#!/usr/bin/env python3
"""Run the Issue #294 downstream matrix with mapping-guarded B/C grouping.

This is an experiment-only entrypoint. It reuses the existing downstream matrix
implementation while keeping A_pinned on the unchanged production
``MeasureNumberingPipeline`` and applying the retained-validated
``MappingGuardedConnectorPositivePipeline`` only to B/C candidate-native grouping.
Production source, config, thresholds, detector dispatch, and MMR logic remain
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue294 import run_downstream_candidate_matrix as matrix
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)


def _run_variant_with_pipeline(
    pipeline_type: type,
    **kwargs: Any,
) -> dict[str, Any]:
    original = matrix.MeasureNumberingPipeline
    matrix.MeasureNumberingPipeline = pipeline_type
    try:
        return matrix._run_downstream_variant(**kwargs)
    finally:
        matrix.MeasureNumberingPipeline = original


def _run_mode(
    *,
    mode: str,
    image: Path,
    detections: dict[str, Path],
    geometry: dict[str, dict[str, Path]],
    support: dict[str, Any],
    output_root: Path,
    detection_config: dict[str, Any],
) -> dict[str, Any]:
    variants: dict[str, dict[str, Any]] = {}
    for label in ("A_pinned", "B_b377", "C_latest"):
        pipeline_type = (
            MeasureNumberingPipeline
            if label == "A_pinned"
            else MappingGuardedConnectorPositivePipeline
        )
        variants[label] = _run_variant_with_pipeline(
            pipeline_type,
            label=label,
            image=image,
            baseline_detection=detections[label],
            support=support,
            staff_mask=geometry[label]["staff"],
            clef_mask=geometry[label]["clef"],
            output_root=output_root / mode,
            detection_config=detection_config,
        )
    return {
        "variants": variants,
        "comparisons_to_A": {
            label: matrix._comparison(variants["A_pinned"], variants[label])
            for label in ("B_b377", "C_latest")
        },
    }


def main() -> int:
    original = matrix._run_mode
    matrix._run_mode = _run_mode
    try:
        return matrix.main()
    finally:
        matrix._run_mode = original


if __name__ == "__main__":
    raise SystemExit(main())
