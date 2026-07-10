"""Production-facing dense detector route.

The dense route is the default detector path.  It rebuilds the high-recall
candidate set from the current run's images and hybrid artifacts, then injects
those candidates into the normal probe/CNN pipeline.  The ordinary route is
available only through the explicit ``detection.route: ordinary`` opt-out.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.pipeline.detector_routes.dense_full_pipeline import (
    FILTER_PARAMS,
    GENERATION_PARAMS,
    DenseRouteArtifacts,
    reconstruct_dense_full_pipeline_route,
)

logger = logging.getLogger(__name__)

DEFAULT_DETECTOR_ROUTE = "dense"
DENSE_ROUTE_PROFILE = "production_dense_v1"
SUPPORTED_DETECTOR_ROUTES = {"dense", "ordinary", "precomputed"}

# These are profile-owned values.  Selecting the dense route means using the
# validated high-accuracy profile rather than inheriting a partial collection
# of per-run defaults.  Paths and environment-specific values remain outside
# this mapping.
DENSE_PROFILE_PARAMETERS: dict[str, Any] = {
    "enable_sr": True,
    "sr_scale": 2,
    "crop_recenter_on_bbox_ink": True,
    "band_source": "row_stats",
    "band_cluster_max_dist": 25.0,
    "ink_threshold": 240,
    "min_ratio": 0.60,
    "min_height_ratio": 0.006,
    "min_width_ratio": 0.0,
    "probe_width": 4,
    "max_per_band": 80,
    "enable_heuristic_filters": True,
    "candidate_filter_kwargs": {
        "left_margin_ratio": 0.12,
        "clef_left_ratio": 0.25,
        "min_height_median_ratio": 0.6,
        "ink_threshold": 180,
        "min_ink_ratio": 0.18,
        "paper_threshold": 200,
        "min_paper_overlap_ratio": 0.6,
        "min_staff_overlap_ratio": 0.02,
    },
    "cnn_threshold": 0.1,
    "cnn_apply_nms": False,
    "divisi_rescue": True,
    "scan_gap_rescue": True,
    "scan_gap_threshold_ratio": 1.5,
    "scan_gap_rescue_min_ratio": 0.3,
    "scan_x_peak_rescue": True,
    "scan_rightmost_rescue": True,
    "scan_center_on_peak": True,
}

DENSE_RUNTIME_KEYS = {
    "precomputed_probe_candidates_root",
    "cnn_bands_from",
    "probe_use_original_images",
    "resolved_route",
}


def resolve_detector_route(det_cfg: dict[str, Any]) -> tuple[str, str]:
    """Resolve detector route and whether it was defaulted or explicit."""
    raw = det_cfg.get("route")
    if raw is not None:
        route = str(raw).strip().lower()
        selection = "explicit"
    elif det_cfg.get("precomputed_probe_candidates_root"):
        # Preserve historical/reproduction configs that explicitly inject
        # candidate artifacts but predate the route selector.
        route = "precomputed"
        selection = "legacy_precomputed_config"
    else:
        route = DEFAULT_DETECTOR_ROUTE
        selection = "default"

    if route not in SUPPORTED_DETECTOR_ROUTES:
        supported = ", ".join(sorted(SUPPORTED_DETECTOR_ROUTES))
        raise ValueError(f"Unsupported detection.route={route!r}; expected one of: {supported}")
    return route, selection


def normalize_runtime_detection_config(config: dict[str, Any]) -> None:
    """Remove stale generated paths before executing a dense rerun.

    Manifests intentionally record resolved route artifacts.  Corrected reruns
    copy source configuration, so those run-local paths must not be reused.
    The route/profile is retained and fresh artifacts are reconstructed.
    """
    detection = config.get("detection")
    if detection is None:
        detection = {}
        config["detection"] = detection
    if not isinstance(detection, dict):
        raise ValueError("detection must be a mapping when provided")

    resolved = detection.get("resolved_route")
    if detection.get("route") is None and isinstance(resolved, dict):
        if resolved.get("profile") == DENSE_ROUTE_PROFILE:
            detection["route"] = "dense"

    route, _ = resolve_detector_route(detection)
    if route == "dense":
        for key in DENSE_RUNTIME_KEYS:
            if key != "resolved_route":
                detection.pop(key, None)
        detection.pop("resolved_route", None)

        # Dense reconstruction requires file-backed images.  The pipeline
        # already writes images by default; this closes the explicit-null hole.
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
        if pdf_options.get("output_dir") is None:
            pdf_options["output_dir"] = "auto"


def apply_dense_profile(det_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Apply profile-owned values and return overwritten-value provenance."""
    overwritten: dict[str, dict[str, Any]] = {}
    for key, value in DENSE_PROFILE_PARAMETERS.items():
        old = det_cfg.get(key)
        if old != value:
            overwritten[key] = {"configured": old, "effective": value}
        # Copy nested structures so callers cannot mutate the profile constant.
        det_cfg[key] = dict(value) if isinstance(value, dict) else value

    det_cfg.setdefault(
        "cnn_model_path",
        "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth",
    )
    return overwritten


def _find_artifact(
    root: Path,
    *,
    stem: str,
    suffixes: tuple[str, ...],
    required: bool,
) -> Path | None:
    matches: list[Path] = []
    for suffix in suffixes:
        matches.extend(root.rglob(f"{stem}{suffix}"))
    if not matches:
        if required:
            raise FileNotFoundError(
                f"Required dense-route artifact not found for {stem}: {suffixes} under {root}"
            )
        return None

    # Match existing runtime behavior: prefer SR masks when both baseline and
    # SR artifacts exist, then use a deterministic lexical order.
    matches = sorted(set(matches), key=lambda path: ("sr" not in path.parts, str(path)))
    return matches[0]


def build_current_run_inventory(
    *,
    images: list[Path],
    hybrid_output_dir: Path,
    route_root: Path,
) -> tuple[Path, Path]:
    """Write an inventory for the current run's images and hybrid artifacts."""
    records: list[dict[str, Any]] = []
    for image in images:
        stem = image.stem
        hybrid_predictions = hybrid_output_dir / "hybrid_results" / f"{stem}_hybrid.json"
        if not hybrid_predictions.exists():
            raise FileNotFoundError(
                f"Hybrid predictions required by dense route are missing: {hybrid_predictions}"
            )

        staff_mask = _find_artifact(
            hybrid_output_dir,
            stem=stem,
            suffixes=(
                "_proxy_debug_3_staff.png",
                "_debug_3_staff.png",
                "_staff_mask.png",
            ),
            required=True,
        )
        clef_mask = _find_artifact(
            hybrid_output_dir,
            stem=stem,
            suffixes=(
                "_proxy_debug_7_clefs_keys.png",
                "_debug_7_clefs_keys.png",
                "_proxy_debug_2_clefs.png",
                "_debug_2_clefs.png",
                "_clef_mask.png",
                "_clefs_keys_mask.png",
            ),
            required=False,
        )

        record: dict[str, Any] = {
            "name": f"{image.parent.name}/{stem}",
            "score": image.parent.name,
            "page": stem,
            "image": str(image),
            "hybrid_predictions": str(hybrid_predictions),
            "staff_mask": str(staff_mask),
            "run_dir": str(staff_mask.parent),
        }
        if clef_mask is not None:
            record["clef_mask"] = str(clef_mask)
        records.append(record)

    inventory = route_root / "current_run_inventory.json"
    exclude = route_root / "current_run_exclude.json"
    route_root.mkdir(parents=True, exist_ok=True)
    inventory.write_text(
        json.dumps({"records": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    exclude.write_text('{"excluded_pages": []}\n', encoding="utf-8")
    return inventory, exclude


def reconstruct_current_run_dense_route(
    *,
    images: list[Path],
    hybrid_output_dir: Path,
    route_root: Path,
    verbose_logs: bool = False,
) -> DenseRouteArtifacts:
    """Reconstruct the dense route from current production-run artifacts."""
    if not images:
        raise ValueError("Dense detector route requires at least one image")
    inventory, exclude = build_current_run_inventory(
        images=images,
        hybrid_output_dir=hybrid_output_dir,
        route_root=route_root,
    )
    artifacts = reconstruct_dense_full_pipeline_route(
        inventory=inventory,
        exclude=exclude,
        route_root=route_root,
        expected_pages=len(images),
        verbose_logs=verbose_logs,
    )
    logger.info(
        "Reconstructed production dense route for %s pages under %s",
        len(images),
        route_root,
    )
    return artifacts


def build_resolved_route_metadata(
    *,
    selection: str,
    artifacts: DenseRouteArtifacts | None,
    overwritten_parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    """Build manifest-safe route provenance."""
    metadata: dict[str, Any] = {
        "name": "dense",
        "profile": DENSE_ROUTE_PROFILE,
        "selection": selection,
        "dry_run": dry_run,
        "profile_parameters": DENSE_PROFILE_PARAMETERS,
        "generation_parameters": GENERATION_PARAMS,
        "filter_parameters": FILTER_PARAMS,
        "overwritten_config_values": overwritten_parameters,
    }
    if artifacts is not None:
        metadata["artifacts"] = {
            "filtered_root": str(artifacts.filtered_root),
            "probe_rescue_root": str(artifacts.probe_rescue_root),
        }
        metadata["execution_summary"] = artifacts.execution_summary
    return metadata
