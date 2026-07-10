"""Default production detection entrypoint.

This wrapper keeps the existing detector implementation but inserts the
production dense candidate reconstruction between hybrid detection and the
probe/CNN stages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.pipeline.detector_routes.production_dense import (
    DENSE_ROUTE_PROFILE,
    apply_dense_profile,
    build_resolved_route_metadata,
    normalize_runtime_detection_config,
    reconstruct_current_run_dense_route,
    resolve_detector_route,
)


def _ensure_file_backed_images(
    images: list[Path],
    in_memory_images: dict[str, Any] | None,
) -> None:
    """Persist virtual PDF-rendered images before dense subprocess steps."""
    missing = [image for image in images if not image.exists()]
    if not missing:
        return
    if not in_memory_images:
        raise FileNotFoundError(
            "Dense detector route requires file-backed images; missing: "
            + ", ".join(str(path) for path in missing)
        )

    from src.pdf_to_images import save_image

    for image_path in missing:
        image = in_memory_images.get(image_path.stem)
        if image is None:
            raise FileNotFoundError(
                f"Dense detector image is absent from disk and cache: {image_path}"
            )
        image_path.parent.mkdir(parents=True, exist_ok=True)
        save_image(image_path, image, fmt=image_path.suffix.lstrip(".") or "png")


def run_detection_step(
    config: dict[str, Any],
    images: list[Path],
    page_ids: list[str],
    run_id: str,
    run_dir: Path,
    *,
    dry_run: bool,
    in_memory_images: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the production detector with dense route as the default."""
    # Import lazily to preserve the package's optional dependency behavior.
    from src.pipeline.detection.orchestrator import DetectorOrchestrator

    detection = config.get("detection")
    if detection is None:
        detection = {}
        config["detection"] = detection
    if not isinstance(detection, dict):
        raise ValueError("detection must be a mapping when provided")

    # A corrected rerun may copy resolved paths from the source manifest.
    # Keep the logical route/profile, but never reuse those run-local artifacts.
    normalize_runtime_detection_config(config)

    orchestrator = DetectorOrchestrator(
        config=config,
        images=images,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )

    route, selection = resolve_detector_route(orchestrator.det_cfg)
    orchestrator.det_cfg["route"] = route

    overwritten: dict[str, dict[str, Any]] = {}
    if route == "dense":
        overwritten = apply_dense_profile(orchestrator.det_cfg)
        if not dry_run:
            _ensure_file_backed_images(images, in_memory_images)

    hybrid_result = orchestrator._run_hybrid_detection()
    orchestrator.hybrid_output_dir = hybrid_result["hybrid_output_dir"]
    orchestrator.commands.extend(hybrid_result["commands"])

    if route == "dense":
        artifacts = None
        if not dry_run:
            artifacts = reconstruct_current_run_dense_route(
                images=images,
                hybrid_output_dir=orchestrator.hybrid_output_dir,
                route_root=run_dir / "intermediate" / "dense_detector_route",
                verbose_logs=bool(orchestrator.det_cfg.get("dense_route_verbose_logs", False)),
            )
            orchestrator.det_cfg.update(
                {
                    "precomputed_probe_candidates_root": str(artifacts.probe_rescue_root),
                    "cnn_bands_from": str(artifacts.filtered_root),
                    "probe_use_original_images": True,
                }
            )
        orchestrator.det_cfg["resolved_route"] = build_resolved_route_metadata(
            selection=selection,
            artifacts=artifacts,
            overwritten_parameters=overwritten,
            dry_run=dry_run,
        )
        orchestrator.commands.append(
            [
                "inprocess:dense_detector_route",
                "--profile",
                DENSE_ROUTE_PROFILE,
                "--selection",
                selection,
            ]
        )
    elif route == "precomputed":
        if not orchestrator.det_cfg.get("precomputed_probe_candidates_root"):
            raise ValueError(
                "detection.route=precomputed requires detection.precomputed_probe_candidates_root"
            )
        orchestrator.det_cfg["resolved_route"] = {
            "name": "precomputed",
            "profile": "external_precomputed",
            "selection": selection,
            "precomputed_probe_candidates_root": str(
                orchestrator.det_cfg["precomputed_probe_candidates_root"]
            ),
            "cnn_bands_from": (
                str(orchestrator.det_cfg["cnn_bands_from"])
                if orchestrator.det_cfg.get("cnn_bands_from")
                else None
            ),
        }
    else:
        orchestrator.det_cfg["resolved_route"] = {
            "name": "ordinary",
            "profile": "legacy_ordinary",
            "selection": selection,
            "warning": ("Explicit low-accuracy opt-out from the production dense detector route."),
        }

    probe_result = orchestrator._run_probe_scan()
    orchestrator.probe_output_dir = probe_result["probe_output_dir"]
    orchestrator.commands.extend(probe_result["commands"])

    cnn_result = orchestrator._run_cnn_scoring()
    orchestrator.commands.extend(cnn_result["commands"])

    return {
        "commands": orchestrator.commands,
        "hybrid_output_dir": orchestrator.hybrid_output_dir,
        "probe_output_dir": orchestrator.probe_output_dir,
        "resolved_route": orchestrator.det_cfg.get("resolved_route"),
        "page_ids": page_ids,
    }
