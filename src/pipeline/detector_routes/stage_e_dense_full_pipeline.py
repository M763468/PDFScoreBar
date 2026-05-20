"""Compatibility shim for the historical Stage E dense route module.

New code should import from ``src.pipeline.detector_routes.dense_full_pipeline``.
This module remains to preserve the #141/#156 Stage E checkpoint import surface.
"""

from pathlib import Path

from src.pipeline.detector_routes.dense_full_pipeline import (  # noqa: F401
    DENSE_ROUTE_EXPECTED_PAGES,
    FILTER_PARAMS,
    GENERATION_PARAMS,
    DenseRouteArtifacts,
    load_route_image_paths,
    reconstruct_dense_full_pipeline_route,
    regenerate_dense_candidates,
    regenerate_probe_rescue_candidates,
)

STAGE_E_EXPECTED_PAGES = DENSE_ROUTE_EXPECTED_PAGES
StageEDenseRouteArtifacts = DenseRouteArtifacts
load_stage_e_image_paths = load_route_image_paths


def regenerate_issue53_candidates(*, image_paths: list[Path], filtered_root: Path, stage_e_root: Path) -> Path:
    """Compatibility wrapper for the historical Issue53-style rescue name."""
    return regenerate_probe_rescue_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        route_root=stage_e_root,
    )


def reconstruct_stage_e_dense_route(
    *,
    inventory: Path,
    exclude: Path,
    stage_e_root: Path,
) -> DenseRouteArtifacts:
    """Compatibility wrapper for the historical Stage E route name."""
    return reconstruct_dense_full_pipeline_route(
        inventory=inventory,
        exclude=exclude,
        route_root=stage_e_root,
    )
