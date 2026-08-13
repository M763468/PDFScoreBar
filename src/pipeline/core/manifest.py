"""Manifest generation."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List

from src.common.connector_artifacts import describe_connector_artifacts


def build_manifest(
    config: Dict[str, Any],
    *,
    run_id: str,
    run_dir: Path,
    images: List[Path],
    page_ids: List[str],
    page_runs: List[str],
    resolved: List[Dict[str, Any]],
    commands: List[List[str]],
    page_statuses: List[Dict[str, Any]],
    barline_override_stats: Dict[str, Dict[str, int]],
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "config": config,
        "pages": [
            {
                "page_id": page_id,
                "image_path": str(image_path),
                "page_run": page_run,
                "barlines_json": resolved_item["barlines_json"],
                "staff_mask": resolved_item["staff_mask"],
                "connector_evidence": describe_connector_artifacts(
                    Path(resolved_item["staff_mask"])
                ),
                "mmr_geometry": resolved_item.get("mmr_staff_geometry"),
                "status": next(
                    (status for status in page_statuses if status["page_id"] == page_id),
                    None,
                ),
                "barline_overrides": barline_override_stats.get(page_id, {}),
            }
            for page_id, image_path, page_run, resolved_item in zip(
                page_ids, images, page_runs, resolved
            )
        ],
        "commands": [{"step": f"command_{i + 1}", "cmd": cmd} for i, cmd in enumerate(commands)],
    }
