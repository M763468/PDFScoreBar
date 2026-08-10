"""Production orchestration for the verified Stage E detector route."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.run_ids import split_score_page_from_composite_stem
from src.pipeline.utils.io import ensure_dir

from .config import get_cnn_apply_nms
from .input_contract import build_detector_input_contract
from .profile_hybrid import VerifiedProfileHybridDetector

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DENSE_ROUTE_NAME = "dense_full_pipeline"


def _first_existing(directory: Path, names: tuple[str, ...], *, description: str) -> Path:
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing {description} in {directory}")


def _score_page(image: Path) -> tuple[str, str]:
    split = split_score_page_from_composite_stem(image.stem)
    return split if split is not None else (image.parent.name, image.stem)


class DetectorOrchestrator:
    """Lightweight supervisor for the verified fresh Stage E route."""

    def __init__(
        self,
        *,
        config: Dict[str, Any],
        images: List[Path],
        run_id: str,
        run_dir: Path,
        dry_run: bool,
        in_memory_images: Dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.images = images
        self.run_id = run_id
        self.run_dir = run_dir
        self.dry_run = dry_run
        self.in_memory_images = in_memory_images
        self.det_cfg = dict(config.get("detection") or {})
        self.detector_route = str(self.det_cfg.get("detector_route", "standard"))
        self.homr_profile = self.det_cfg.get("homr_profile")
        self.skip_existing = bool(self.det_cfg.get("probe_skip_existing", False))
        self.input_contract = build_detector_input_contract(self.det_cfg)
        self.input_contract_path = self.run_dir / "intermediate" / "detector_input_contract.json"
        self.hybrid_output_dir: Path | None = None
        self.probe_output_dir: Path | None = None
        self._dense_route: Any | None = None

        if self.detector_route != DENSE_ROUTE_NAME:
            raise ValueError(
                f"Verified Stage E orchestrator requires detector_route={DENSE_ROUTE_NAME}"
            )
        if not self.homr_profile:
            raise ValueError("Verified Stage E production route requires detection.homr_profile")
        if in_memory_images:
            raise ValueError("Verified Stage E production route requires persisted image files")

    def _record_input_contract(self) -> Path | None:
        if self.dry_run:
            return None
        ensure_dir(self.input_contract_path.parent)
        self.input_contract_path.write_text(
            json.dumps(self.input_contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return self.input_contract_path

    def _run_hybrid_detection(self) -> Dict[str, Any]:
        detector = VerifiedProfileHybridDetector(
            det_cfg=self.det_cfg,
            images=self.images,
            run_id=self.run_id,
            project_root=PROJECT_ROOT,
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
            score, page = _score_page(image)
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
                    "score": score,
                    "page": page,
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

    def _run_dense_route(self) -> Dict[str, Any]:
        if self.dry_run:
            probe_root = (
                self.run_dir
                / "intermediate"
                / "dense_full_pipeline_route"
                / "probe_rescue_candidates"
            )
            return {
                "commands": [["inprocess:dense_full_pipeline_route", "--dry-run"]],
                "probe_output_dir": probe_root,
            }

        # Import the dense implementation only after x4 source generation has
        # completed and its disposable support workers have exited.
        from src.pipeline.detector_routes.dense_full_pipeline import (
            reconstruct_dense_full_pipeline_route,
        )

        inventory, exclude = self._write_dense_inventory()
        route_root = self.run_dir / "intermediate" / "dense_full_pipeline_route"
        self._dense_route = reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=route_root,
            expected_pages=len(self.images),
        )
        summary = self._dense_route.execution_summary or {}
        return {
            "commands": [
                [
                    "inprocess:dense_full_pipeline_route",
                    "--inventory",
                    str(inventory),
                    "--summary",
                    str(summary.get("summary_path", "")),
                ]
            ],
            "probe_output_dir": self._dense_route.probe_rescue_root,
        }

    def _run_cnn_scoring(self) -> Dict[str, Any]:
        if self._dense_route is None and not self.dry_run:
            raise RuntimeError("Dense detector route was not reconstructed before CNN scoring")
        cnn_model = self.det_cfg.get("cnn_model_path")
        if not cnn_model:
            raise ValueError("detection.cnn_model_path is required")
        if get_cnn_apply_nms(self.det_cfg):
            raise ValueError("Verified Stage E detector route requires cnn_apply_nms=false")
        bands_from = (
            self._dense_route.filtered_root
            if self._dense_route is not None
            else self.run_dir
            / "intermediate"
            / "dense_full_pipeline_route"
            / "probe_candidates_filtered"
        )
        if not self.dry_run:
            if self.probe_output_dir is None:
                raise RuntimeError("Probe output root is missing")
            # Keep torch/torchvision out of the supervisor until the x4 support
            # workers and verified HOMR profile runs have completed.
            from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

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

    def run_detection(self) -> Dict[str, Any]:
        contract_path = self._record_input_contract()
        commands: list[list[str]] = []

        hybrid_result = self._run_hybrid_detection()
        self.hybrid_output_dir = Path(hybrid_result["hybrid_output_dir"])
        commands.extend(hybrid_result.get("commands", []))

        dense_result = self._run_dense_route()
        self.probe_output_dir = Path(dense_result["probe_output_dir"])
        commands.extend(dense_result.get("commands", []))

        cnn_result = self._run_cnn_scoring()
        commands.extend(cnn_result.get("commands", []))

        return {
            "commands": commands,
            "hybrid_output_dir": self.hybrid_output_dir,
            "probe_output_dir": self.probe_output_dir,
            "detector_input_contract": self.input_contract,
            "detector_input_contract_path": contract_path,
            "detector_route": self.detector_route,
            "homr_profile": self.homr_profile,
            "historical_detector_artifact_runtime_input": False,
            "source_generation_phases": hybrid_result.get("source_generation_phases", []),
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
    """Run the verified Stage E detector from fresh upstream inputs."""
    if len(images) != len(page_ids):
        raise ValueError("images/page_ids length mismatch")
    orchestrator = DetectorOrchestrator(
        config=config,
        images=images,
        run_id=run_id,
        run_dir=run_dir,
        dry_run=dry_run,
        in_memory_images=in_memory_images,
    )
    return orchestrator.run_detection()
