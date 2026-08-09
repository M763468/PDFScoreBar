"""Production orchestration for the verified Stage E detector route."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.detector_routes.dense_full_pipeline import (
    DenseRouteArtifacts,
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.utils.io import ensure_dir

from .config import get_cnn_apply_nms
from .orchestrator import DetectorOrchestrator as BaseDetectorOrchestrator
from .profile_hybrid import VerifiedProfileHybridDetector

DENSE_ROUTE_NAME = "dense_full_pipeline"


def _first_existing(directory: Path, names: tuple[str, ...], *, description: str) -> Path:
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing {description} in {directory}")


class DetectorOrchestrator(BaseDetectorOrchestrator):
    """Extend the standard detector with the verified fresh Stage E route."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.detector_route = str(self.det_cfg.get("detector_route", "standard"))
        self.homr_profile = self.det_cfg.get("homr_profile")
        self._dense_route: DenseRouteArtifacts | None = None
        if self.detector_route == DENSE_ROUTE_NAME and not self.homr_profile:
            raise ValueError("dense_full_pipeline production route requires detection.homr_profile")

    def _run_hybrid_detection(self) -> Dict[str, Any]:
        if not self.homr_profile:
            return super()._run_hybrid_detection()
        detector = VerifiedProfileHybridDetector(
            det_cfg=self.det_cfg,
            images=self.images,
            run_id=self.run_id,
            project_root=self.PROJECT_ROOT if hasattr(self, "PROJECT_ROOT") else Path(__file__).resolve().parents[3],
            dry_run=self.dry_run,
            skip_existing=self.skip_existing,
            in_memory_images=self.in_memory_images,
            profile_name=str(self.homr_profile),
        )
        return detector.run()

    def _write_dense_inventory(self) -> tuple[Path, Path]:
        if self.hybrid_output_dir is None:
            raise RuntimeError("Hybrid output is required before dense route reconstruction")
        records = []
        for image in self.images:
            stem = image.stem
            baseline_page = self.hybrid_output_dir / "baseline" / "batch" / stem
            hybrid = self.hybrid_output_dir / "hybrid_results" / f"{stem}_hybrid.json"
            if not hybrid.is_file():
                raise FileNotFoundError(hybrid)
            staff_mask = _first_existing(
                baseline_page,
                (
                    f"{stem}_proxy_debug_3_staff.png",
                    f"{stem}_debug_3_staff.png",
                    f"{stem}_staff_mask.png",
                ),
                description="baseline staff mask",
            )
            clef_mask = _first_existing(
                baseline_page,
                (
                    f"{stem}_proxy_debug_7_clefs_keys.png",
                    f"{stem}_debug_7_clefs_keys.png",
                    f"{stem}_clef_mask.png",
                ),
                description="baseline clef mask",
            )
            records.append(
                {
                    "score": image.parent.name,
                    "page": stem,
                    "image": str(image.resolve()),
                    "hybrid_predictions": str(hybrid.resolve()),
                    "staff_mask": str(staff_mask.resolve()),
                    "clef_mask": str(clef_mask.resolve()),
                    "run_dir": str(baseline_page.resolve()),
                }
            )

        route_input_root = self.run_dir / "intermediate" / "dense_full_pipeline_inputs"
        ensure_dir(route_input_root)
        inventory = route_input_root / "inventory.json"
        exclude = route_input_root / "exclude.json"
        inventory.write_text(
            json.dumps(
                {
                    "schema_version": "pipeline.detector_routes.current_run_inventory.v1",
                    "historical_detector_artifact_runtime_input": False,
                    "records": records,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        exclude.write_text('{"excluded_pages": []}\n', encoding="utf-8")
        return inventory, exclude

    def _run_probe_scan(self) -> Dict[str, Any]:
        if self.detector_route != DENSE_ROUTE_NAME:
            return super()._run_probe_scan()
        if self.dry_run:
            probe_root = self.run_dir / "intermediate" / "dense_full_pipeline_route" / "probe_rescue_candidates"
            return {
                "commands": [["inprocess:dense_full_pipeline_route", "--dry-run"]],
                "probe_output_dir": probe_root,
            }

        inventory, exclude = self._write_dense_inventory()
        route_root = self.run_dir / "intermediate" / "dense_full_pipeline_route"
        self._dense_route = reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=route_root,
            expected_pages=len(self.images),
        )
        return {
            "commands": [
                [
                    "inprocess:dense_full_pipeline_route",
                    "--inventory",
                    str(inventory),
                    "--summary",
                    str(self._dense_route.execution_summary.get("summary_path", "")),
                ]
            ],
            "probe_output_dir": self._dense_route.probe_rescue_root,
        }

    def _run_cnn_scoring(self) -> Dict[str, Any]:
        if self.detector_route != DENSE_ROUTE_NAME:
            return super()._run_cnn_scoring()
        if self._dense_route is None and not self.dry_run:
            raise RuntimeError("Dense detector route was not reconstructed before CNN scoring")

        cnn_model = self.det_cfg.get("cnn_model_path")
        if not cnn_model:
            raise ValueError("detection.cnn_model_path is required")
        cnn_apply_nms = get_cnn_apply_nms(self.det_cfg)
        if cnn_apply_nms:
            raise ValueError("Verified Stage E detector route requires cnn_apply_nms=false")
        bands_from = (
            self._dense_route.filtered_root
            if self._dense_route is not None
            else self.run_dir / "intermediate" / "dense_full_pipeline_route" / "probe_candidates_filtered"
        )
        if not self.dry_run:
            if self.probe_output_dir is None:
                raise RuntimeError("Probe output root is missing")
            run_cnn_scoring_batch(
                probe_output_root=self.probe_output_dir,
                images=self.images,
                model_path=Path(str(cnn_model)),
                threshold=float(self.det_cfg.get("cnn_threshold", 0.1)),
                score_name=(
                    str(self.det_cfg["probe_score_name"])
                    if self.det_cfg.get("probe_score_name")
                    else None
                ),
                crop_recenter_on_bbox_ink=bool(
                    self.det_cfg.get("crop_recenter_on_bbox_ink", False)
                ),
                crop_recenter_max_shift_unit_ratio=float(
                    self.det_cfg.get("crop_recenter_max_shift_unit_ratio", 0.35)
                ),
                input_image_scale=1.0,
                bands_from=bands_from,
                staff_vov_threshold=float(self.det_cfg.get("staff_vov_threshold", 0.5)),
                apply_nms_enabled=False,
                in_memory_images=self.in_memory_images,
            )
        return {
            "commands": [
                [
                    "inprocess:cnn_scoring",
                    "--route",
                    DENSE_ROUTE_NAME,
                    "--bands-from",
                    str(bands_from),
                    "--input-image-scale",
                    "1.0",
                    "--apply-nms",
                    "False",
                ]
            ]
        }


def run_detection_step(
    config: Dict[str, Any],
    images: List[Path],
    page_ids: List[str],
    run_id: str,
    run_dir: Path,
    *,
    dry_run: bool,
    in_memory_images: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run standard or verified Stage E detection from fresh upstream inputs."""
    del page_ids
    orchestrator = DetectorOrchestrator(
        config=config,
        images=images,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )
    result = orchestrator.run_detection()
    result["detector_route"] = orchestrator.detector_route
    result["homr_profile"] = orchestrator.homr_profile
    return result
