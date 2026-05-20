"""Compatibility shim for the historical Stage E dense route module.

New code should import from ``src.pipeline.detector_routes.dense_full_pipeline``.
This module remains to preserve the #141/#156 Stage E checkpoint import surface.
"""

from dataclasses import dataclass
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
load_stage_e_image_paths = load_route_image_paths


@dataclass(frozen=True)
class StageEDenseRouteArtifacts:
    """Historical Stage E artifact view with legacy field access."""

    image_paths: list[Path]
    filtered_root: Path
    probe_rescue_root: Path

    @property
    def issue53_root(self) -> Path:
        """Legacy name for Stage E Issue53-style probe-rescue candidates."""
        return self.probe_rescue_root

    @classmethod
    def from_dense(cls, artifacts: DenseRouteArtifacts) -> "StageEDenseRouteArtifacts":
        return cls(
            image_paths=artifacts.image_paths,
            filtered_root=artifacts.filtered_root,
            probe_rescue_root=artifacts.probe_rescue_root,
        )


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
) -> StageEDenseRouteArtifacts:
    """Compatibility wrapper for the historical Stage E route name."""
    return StageEDenseRouteArtifacts.from_dense(
        reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=stage_e_root,
        )
    )
