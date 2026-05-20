"""Dense full-pipeline detector route support.

This module reconstructs detector-route inputs from current-run inventory data,
then exposes them through the production ``DetectorOrchestrator`` config/API.
The default constants preserve the Stage E / Issue #141 checkpoint behavior;
those historical references are provenance, not public API names.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.pipeline.steps.probe_scan import run_probe_scan_batch

logger = logging.getLogger(__name__)

DENSE_ROUTE_EXPECTED_PAGES = 68

GENERATION_PARAMS = {
    "band_source": "row_stats",
    "band_cluster_max_dist": "25.0",
    "ink_threshold": "240",
    "min_ratio": "0.6",
    "min_height_ratio": "0.006",
    "min_width_ratio": "0.0",
    "probe_width": "4",
    "max_per_band": "80",
    "band_scan_line_ratio": "0.6",
    "band_scan_min_lines": "5",
}

FILTER_PARAMS = {
    "left_margin_ratio": "0.12",
    "clef_left_ratio": "0.25",
    "min_height_median_ratio": "0.6",
    "ink_threshold": "180",
    "min_ink_ratio": "0.18",
    "paper_threshold": "200",
    "min_paper_overlap_ratio": "0.6",
    "min_staff_overlap_ratio": "0.02",
}


@dataclass(frozen=True)
class DenseRouteArtifacts:
    """Freshly reconstructed dense route inputs."""

    image_paths: list[Path]
    filtered_root: Path
    probe_rescue_root: Path

    @property
    def issue53_root(self) -> Path:
        """Legacy name for the historical Issue53-style probe-rescue root."""
        return self.probe_rescue_root


# Compatibility alias for the historical Stage E checkpoint module/API.
StageEDenseRouteArtifacts = DenseRouteArtifacts
STAGE_E_EXPECTED_PAGES = DENSE_ROUTE_EXPECTED_PAGES


def _add_params(cmd: list[str], params: dict[str, str]) -> None:
    for key, value in params.items():
        cmd.extend([f"--{key.replace('_', '-')}", value])


def _run_command(cmd: list[str], *, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("+ %s > %s", " ".join(cmd), log_path)
    with log_path.open("w", encoding="utf-8") as log_file:
        subprocess.run(cmd, check=True, stdout=log_file, stderr=subprocess.STDOUT)


def load_route_image_paths(
    *,
    inventory: Path,
    exclude: Path,
    expected_pages: int = DENSE_ROUTE_EXPECTED_PAGES,
) -> list[Path]:
    """Load the detector-route image list from a benchmark inventory."""
    inv = json.loads(inventory.read_text())
    exclude_list = []
    if exclude.exists():
        exclude_list = json.loads(exclude.read_text()).get("excluded_pages", [])

    image_paths: list[Path] = []
    for rec in inv.get("records", []):
        score = rec["score"]
        page = rec["page"]
        if {"score": score, "page": page} in exclude_list:
            continue
        image_paths.append(Path(rec["image"]))

    if len(image_paths) != expected_pages:
        raise RuntimeError(f"Expected {expected_pages} dense-route images, got {len(image_paths)}")
    return image_paths


# Compatibility alias for the historical Stage E runner/API.
load_stage_e_image_paths = load_route_image_paths


def _resolve_route_root(*, route_root: Path | None, stage_e_root: Path | None) -> Path:
    resolved = route_root if route_root is not None else stage_e_root
    if resolved is None:
        raise TypeError("route_root is required")
    return resolved


def regenerate_dense_candidates(
    *,
    inventory: Path,
    exclude: Path,
    route_root: Path | None = None,
    stage_e_root: Path | None = None,
) -> Path:
    """Regenerate the dense candidate/filter root inside this route run."""
    resolved_route_root = _resolve_route_root(route_root=route_root, stage_e_root=stage_e_root)
    dense_root = resolved_route_root / "dense_candidate_reconstruction"
    raw_root = dense_root / "probe_candidates_from_inventory"
    filtered_root = dense_root / "probe_candidates_filtered"
    suggestions_root = dense_root / "filter_suggestions"
    generation_summary = dense_root / "probe_generation_summary.json"
    filter_summary = dense_root / "filter_apply_summary.json"
    log_dir = dense_root / "logs"

    if dense_root.exists():
        shutil.rmtree(dense_root)
    dense_root.mkdir(parents=True, exist_ok=True)

    gen_cmd = [
        sys.executable,
        "tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py",
        "--inventory",
        str(inventory),
        "--exclude",
        str(exclude),
        "--output-root",
        str(raw_root),
        "--summary-out",
        str(generation_summary),
    ]
    _add_params(gen_cmd, GENERATION_PARAMS)
    _run_command(gen_cmd, log_path=log_dir / "01_generate_probe_candidates.log")

    filter_cmd = [
        sys.executable,
        "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py",
        "--inventory",
        str(inventory),
        "--exclude",
        str(exclude),
        "--candidates-root",
        str(raw_root),
        "--output-root",
        str(filtered_root),
        "--suggestions-root",
        str(suggestions_root),
        "--summary-out",
        str(filter_summary),
    ]
    _add_params(filter_cmd, FILTER_PARAMS)
    _run_command(filter_cmd, log_path=log_dir / "02_apply_candidate_filter.log")

    summary = json.loads(filter_summary.read_text())
    if summary.get("processed") != DENSE_ROUTE_EXPECTED_PAGES or summary.get("errors") != 0:
        raise RuntimeError(
            "Dense candidate reconstruction did not complete cleanly: "
            f"processed={summary.get('processed')} errors={summary.get('errors')}"
        )
    return filtered_root


def regenerate_probe_rescue_candidates(
    *,
    image_paths: list[Path],
    filtered_root: Path,
    route_root: Path | None = None,
    stage_e_root: Path | None = None,
) -> Path:
    """Regenerate probe-rescue candidates for the dense detector route.

    This preserves the historical Issue53-style rescue behavior while exposing
    the runtime output as a semantic precomputed-probe-candidates root.
    """
    resolved_route_root = _resolve_route_root(route_root=route_root, stage_e_root=stage_e_root)
    probe_rescue_root = resolved_route_root / "dense_candidate_reconstruction" / "probe_rescue_candidates"
    legacy_issue53_root = resolved_route_root / "dense_candidate_reconstruction" / "issue53_probe_rescue_candidates"
    shutil.rmtree(probe_rescue_root, ignore_errors=True)
    shutil.rmtree(legacy_issue53_root, ignore_errors=True)
    probe_rescue_root.mkdir(parents=True, exist_ok=True)

    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }
    processed = run_probe_scan_batch(
        images=image_paths,
        output_root=probe_rescue_root,
        bands_from=filtered_root,
        staff_mask_dir=None,
        clef_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        detect_probe_kwargs=detect_probe_kwargs,
        enable_heuristic_filters=False,
    )
    expected_pages = len(image_paths)
    if processed != expected_pages:
        raise RuntimeError(f"Probe-rescue candidate reconstruction processed {processed}/{expected_pages} pages")
    return probe_rescue_root


def regenerate_issue53_candidates(*, image_paths: list[Path], filtered_root: Path, stage_e_root: Path) -> Path:
    """Compatibility wrapper for the historical Issue53-style rescue name."""
    return regenerate_probe_rescue_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        stage_e_root=stage_e_root,
    )


def reconstruct_dense_full_pipeline_route(
    *,
    inventory: Path,
    exclude: Path,
    route_root: Path,
) -> DenseRouteArtifacts:
    """Rebuild all dense full-pipeline detector inputs from current-run sources."""
    image_paths = load_route_image_paths(inventory=inventory, exclude=exclude)
    filtered_root = regenerate_dense_candidates(
        inventory=inventory,
        exclude=exclude,
        route_root=route_root,
    )
    probe_rescue_root = regenerate_probe_rescue_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        route_root=route_root,
    )
    return DenseRouteArtifacts(
        image_paths=image_paths,
        filtered_root=filtered_root,
        probe_rescue_root=probe_rescue_root,
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
