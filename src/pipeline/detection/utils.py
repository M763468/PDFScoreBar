"""Utility functions for path resolution and system monitoring in detection."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.config import get_nested

logger = logging.getLogger(__name__)


def resolve_paths_from_detection(
    config: Dict[str, Any],
    probe_output_dir: Path,
    hybrid_output_dir: Path,
    page_ids: List[str],
    images: List[Path],
) -> List[Dict[str, str]]:
    """Resolves output paths for barlines and staff masks after detection."""
    resolved: List[Dict[str, str]] = []

    det_cfg = get_nested(config, "detection", default={}) or {}
    staff_mask_dir_override = det_cfg.get("staff_mask_dir", "DEFAULT_SENTINEL")
    if staff_mask_dir_override == "DEFAULT_SENTINEL":
        resolved_staff_mask_dir = hybrid_output_dir
    elif staff_mask_dir_override is None:
        resolved_staff_mask_dir = None
    else:
        resolved_staff_mask_dir = Path(staff_mask_dir_override)

    staff_mask_map: Dict[str, Path] = {}
    if resolved_staff_mask_dir is not None and resolved_staff_mask_dir.exists():
        # Pattern 1: *_debug_3_staff.png (Proxy/SR output)
        for path in resolved_staff_mask_dir.rglob("*_debug_3_staff.png"):
            name = path.name
            stem = name.replace("_proxy_debug_3_staff.png", "").replace("_debug_3_staff.png", "")
            staff_mask_map[stem] = path
        # Pattern 2: *_staff_mask.png (Baseline in-process output)
        for path in resolved_staff_mask_dir.rglob("*_staff_mask.png"):
            name = path.name
            stem = name.replace("_staff_mask.png", "")
            if stem not in staff_mask_map:
                staff_mask_map[stem] = path

    for page_id, img_path in zip(page_ids, images):
        stem = img_path.stem

        candidate_dirs = list(probe_output_dir.glob(f"*_{stem}"))
        if not candidate_dirs:
            candidate_dirs = list(probe_output_dir.glob(f"*{stem}*"))

        barlines_path = None
        if candidate_dirs:
            target_dir = candidate_dirs[0]
            barlines_path = target_dir / "pipeline2_no_peak_filtered_cnn.json"

        if not barlines_path or not barlines_path.exists():
            hybrid_batch_json = hybrid_output_dir / "hybrid_results" / f"{stem}_hybrid.json"
            if hybrid_batch_json.exists():
                barlines_path = hybrid_batch_json

        staff_mask_path = staff_mask_map.get(stem)

        if not barlines_path or not barlines_path.exists():
            logger.warning(f"Warning: Barlines not found for {page_id} (stem: {stem})")
            barlines_path = Path("MISSING_BARLINES.json")

        if resolved_staff_mask_dir is not None and (
            not staff_mask_path or not staff_mask_path.exists()
        ):
            logger.warning(f"Warning: Staff mask not found for {page_id} (stem: {stem})")
            staff_mask_path = Path("MISSING_STAFF_MASK.png")
        elif resolved_staff_mask_dir is None:
            # Explicitly disabled
            staff_mask_path = Path("DISABLED_STAFF_MASK.png")

        resolved.append(
            {
                "page_id": page_id,
                "page_run": stem,
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )

    return resolved


def resolve_barlines_and_masks_config(
    config: Dict[str, Any],
    page_ids: List[str],
    page_runs: List[str],
    *,
    excluded_page_ids: set[str] | None = None,
) -> List[Dict[str, str]]:
    """Resolves paths based on configuration when detection is skipped."""
    barlines_root = get_nested(config, "inputs", "barlines_root")
    barlines_pattern = get_nested(config, "inputs", "barlines_pattern")
    staff_mask_pattern = get_nested(config, "inputs", "staff_mask_pattern")
    if not barlines_root or not barlines_pattern or not staff_mask_pattern:
        raise ValueError("inputs.barlines_root/pattern and inputs.staff_mask_pattern are required.")

    resolved = []
    for page_id, page_run in zip(page_ids, page_runs):
        if excluded_page_ids and page_id in excluded_page_ids:
            resolved.append(
                {
                    "page_id": page_id,
                    "page_run": page_run,
                    "barlines_json": "MISSING_BARLINES.json",
                    "staff_mask": "MISSING_STAFF_MASK.png",
                }
            )
            continue

        barlines_path = Path(barlines_root) / barlines_pattern.format(
            page_run=page_run, page_id=page_id
        )
        staff_mask_path = Path(barlines_root) / staff_mask_pattern.format(
            page_run=page_run, page_id=page_id
        )

        resolved.append(
            {
                "page_id": page_id,
                "page_run": page_run,
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )
    return resolved


def log_vram_usage(message: str = ""):
    """Logs current GPU memory usage if available."""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            used, total = res.stdout.strip().split(",")
            logger.info(f"VRAM Usage ({message}): {used.strip()} / {total.strip()} MiB")
    except Exception as e:
        logger.debug(f"Could not get VRAM usage: {e}")
