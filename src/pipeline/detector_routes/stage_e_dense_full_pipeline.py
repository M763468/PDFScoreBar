"""Compatibility shim for the historical Stage E dense route module.

New code should import from ``src.pipeline.detector_routes.dense_full_pipeline``.
This module remains to preserve the #141/#156 Stage E checkpoint import surface.
"""

from src.pipeline.detector_routes.dense_full_pipeline import (  # noqa: F401
    DENSE_ROUTE_EXPECTED_PAGES,
    FILTER_PARAMS,
    GENERATION_PARAMS,
    STAGE_E_EXPECTED_PAGES,
    DenseRouteArtifacts,
    StageEDenseRouteArtifacts,
    load_route_image_paths,
    load_stage_e_image_paths,
    reconstruct_dense_full_pipeline_route,
    reconstruct_stage_e_dense_route,
    regenerate_dense_candidates,
    regenerate_issue53_candidates,
    regenerate_probe_rescue_candidates,
)
