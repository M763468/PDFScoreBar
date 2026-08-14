"""Fresh current-runtime staff-mask support for Phase B MMR geometry."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Set

from src.pipeline.core.config import get_nested
from src.pipeline.core.python_env import get_pipeline_python
from src.pipeline.core.subprocess_utils import run_with_logging
from src.pipeline.utils.io import load_json

PRODUCER = "HybridDetector._run_homr_in_process"
PRODUCER_RUNTIME = "current_pipeline_homr"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_PROJECT_ROOT = Path("/workspace")

logger = logging.getLogger(__name__)


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
        output_root = page_root / "homr"
        overrides_mmr = page_ctx[page_id]["intermediate_dir"] / "overrides_mmr.json"
        mmr_already_complete = orchestrator.skip_existing and overrides_mmr.is_file()

        command = _resolve_worker_command(image, page_root)
        docker_exec = _uses_docker_exec(command)
        worker_image = _worker_visible_path(image, docker_exec=docker_exec)
        worker_output_root = _worker_visible_path(output_root, docker_exec=docker_exec)
        worker_request_path = _worker_visible_path(request_path, docker_exec=docker_exec)
        worker_result_path = _worker_visible_path(result_path, docker_exec=docker_exec)

        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "pipeline.mmr_staff_geometry_request.v1",
                    "detection": detection,
                    "images": [worker_image],
                    "output_root": worker_output_root,
                    "skip_existing": orchestrator.skip_existing,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

        loaded = _try_load_result(
            skip_existing=orchestrator.skip_existing,
            result_path=result_path,
            worker_image=worker_image,
            docker_exec=docker_exec,
        )
        if loaded is None:
            run_with_logging(
                command
                + [
                    "-m",
                    "src.pipeline.detection.mmr_staff_geometry_worker",
                    "--request",
                    worker_request_path,
                    "--result",
                    worker_result_path,
                ],
                check=True,
            )
            payload, staff_mask = _load_result(
                result_path,
                worker_image=worker_image,
                docker_exec=docker_exec,
            )
        else:
            payload, staff_mask = loaded

        _hydrate_provenance(
            page_ctx[page_id],
            staff_mask=staff_mask,
            payload=payload,
            result_path=result_path,
        )
        if not mmr_already_complete:
            resolved[page_id] = staff_mask

    return resolved


def _resolve_worker_command(image: Path, page_root: Path) -> list[str]:
    command = get_pipeline_python("homr")
    if not _uses_docker_exec(command):
        return command

    inaccessible = [path for path in (image, page_root) if not _is_project_path(path)]
    if not inaccessible:
        return command

    logger.warning(
        "External path is not visible through the /workspace Docker mount; "
        "falling back to host Python for MMR staff geometry: %s",
        ", ".join(str(path) for path in inaccessible),
    )
    return [os.environ.get("PIPELINE_PYTHON", sys.executable)]


def _uses_docker_exec(command: list[str]) -> bool:
    return len(command) >= 2 and command[0] == "docker" and command[1] == "exec"


def _is_project_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return False
    return True


def _worker_visible_path(path: Path, *, docker_exec: bool) -> str:
    resolved = path.resolve()
    if not docker_exec:
        return str(resolved)
    try:
        relative = resolved.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise ValueError(f"Path is not visible through the /workspace mount: {resolved}") from error
    return str(CONTAINER_PROJECT_ROOT / relative)


def _host_visible_path(value: Any, *, docker_exec: bool) -> Path:
    path = Path(str(value))
    if not docker_exec:
        return path
    try:
        relative = path.relative_to(CONTAINER_PROJECT_ROOT)
    except ValueError as error:
        raise ValueError(f"Docker worker returned a path outside /workspace: {path}") from error
    return PROJECT_ROOT / relative


def _try_load_result(
    *,
    skip_existing: bool,
    result_path: Path,
    worker_image: str,
    docker_exec: bool,
) -> tuple[Mapping[str, Any], Path] | None:
    if not skip_existing or not result_path.is_file():
        return None
    try:
        return _load_result(
            result_path,
            worker_image=worker_image,
            docker_exec=docker_exec,
        )
    except (OSError, ValueError, TypeError):
        return None


def _load_result(
    result_path: Path,
    *,
    worker_image: str,
    docker_exec: bool,
) -> tuple[Mapping[str, Any], Path]:
    payload = load_json(result_path)
    masks = _validated_masks(payload, result_path)
    value = masks.get(worker_image)
    if not value:
        raise ValueError(f"MMR staff-geometry result lacks image: {worker_image}")
    staff_mask = _host_visible_path(value, docker_exec=docker_exec)
    if not staff_mask.is_file():
        raise FileNotFoundError(staff_mask)
    return payload, staff_mask


def _hydrate_provenance(
    ctx: Dict[str, Any],
    *,
    staff_mask: Path,
    payload: Mapping[str, Any],
    result_path: Path,
) -> None:
    ctx["mmr_staff_mask"] = staff_mask
    ctx["resolved"]["mmr_staff_mask"] = str(staff_mask)
    ctx["resolved"]["mmr_staff_geometry"] = {
        "staff_mask": str(staff_mask),
        "producer": payload["producer"],
        "producer_runtime": payload.get("producer_runtime"),
        "historical_detector_artifact_runtime_input": False,
        "result_path": str(result_path),
    }


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
