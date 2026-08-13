"""Fresh current-runtime staff-mask support for Phase B MMR geometry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Set

from src.pipeline.core.config import get_nested
from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.utils.io import load_json


PRODUCER = "HybridDetector._run_homr_in_process"
PRODUCER_RUNTIME = "current_pipeline_homr"


def prepare_mmr_staff_masks(
    orchestrator: Any,
    page_ids: List[str],
    excluded_page_ids: Set[str],
    page_ctx: Dict[str, Dict[str, Any]],
) -> dict[str, Path]:
    targets = [
        page_id
        for page_id in page_ids
        if page_id not in excluded_page_ids
        and Path(page_ctx[page_id]["numbering_base"]).is_file()
        and not (
            orchestrator.skip_existing
            and (page_ctx[page_id]["intermediate_dir"] / "overrides_mmr.json").exists()
        )
    ]
    if not targets:
        return {}

    root = orchestrator.intermediate_dir / "mmr_staff_geometry"
    root.mkdir(parents=True, exist_ok=True)
    detection = dict(get_nested(orchestrator.config, "detection", default={}) or {})
    resolved: dict[str, Path] = {}

    for page_id in targets:
        image = Path(page_ctx[page_id]["image_path"]).resolve()
        page_root = root / page_id
        page_root.mkdir(parents=True, exist_ok=True)
        request_path = page_root / "request.json"
        result_path = page_root / "result.json"
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "pipeline.mmr_staff_geometry_request.v1",
                    "detection": detection,
                    "images": [str(image)],
                    "output_root": str((page_root / "homr").resolve()),
                    "skip_existing": orchestrator.skip_existing,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

        if not _can_reuse_result(orchestrator.skip_existing, result_path, [image]):
            command = get_pipeline_python("homr") + [
                "-m",
                "src.pipeline.detection.mmr_staff_geometry_worker",
                "--request",
                str(request_path),
                "--result",
                str(result_path),
            ]
            run_with_logging(command, check=True)

        payload = load_json(result_path)
        masks = _validated_masks(payload, result_path)
        value = masks.get(str(image))
        if not value:
            raise ValueError(f"MMR staff-geometry result lacks image: {image}")
        staff_mask = Path(str(value))
        if not staff_mask.is_file():
            raise FileNotFoundError(staff_mask)

        resolved[page_id] = staff_mask
        page_ctx[page_id]["mmr_staff_mask"] = staff_mask
        page_ctx[page_id]["resolved"]["mmr_staff_mask"] = str(staff_mask)
        page_ctx[page_id]["resolved"]["mmr_staff_geometry"] = {
            "staff_mask": str(staff_mask),
            "producer": payload["producer"],
            "producer_runtime": payload.get("producer_runtime"),
            "historical_detector_artifact_runtime_input": False,
            "result_path": str(result_path),
        }

    return resolved


def _can_reuse_result(skip_existing: bool, result_path: Path, images: list[Path]) -> bool:
    if not skip_existing or not result_path.is_file():
        return False
    try:
        masks = _validated_masks(load_json(result_path), result_path)
    except (OSError, ValueError, TypeError):
        return False
    return all(
        str(image) in masks and Path(str(masks[str(image)])).is_file()
        for image in images
    )


def _validated_masks(payload: Any, result_path: Path) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete MMR staff-geometry result: {result_path}")
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("MMR staff geometry must not use historical detector artifacts")
    if payload.get("producer") != PRODUCER:
        raise ValueError(f"Unexpected MMR staff-geometry producer: {payload.get('producer')}")
    if payload.get("producer_runtime") != PRODUCER_RUNTIME:
        raise ValueError(
            f"Unexpected MMR staff-geometry runtime: {payload.get('producer_runtime')}"
        )
    masks = payload.get("staff_masks")
    if not isinstance(masks, Mapping):
        raise ValueError("MMR staff-geometry result lacks staff_masks")
    return masks
