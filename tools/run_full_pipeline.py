#!/usr/bin/env python3
"""
DEPRECATED: This orchestrator is legacy. 
Please use 'python -m src.pipeline.main' instead for integrated features and model persistence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Add project root to path to allow imports from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

import cv2  # noqa: E402

from src.common.barline_evaluation import (  # noqa: E402
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
    barline_iou,
)


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML is required. Install it in the current environment.") from exc
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping.")
    return data


def _get_nested(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _build_pdf_command(config: Dict[str, Any], run_dir: Path) -> List[str]:
    pdf_path = _get_nested(config, "inputs", "pdf_path")
    pdf_opts = _get_nested(config, "inputs", "pdf_to_images", default={}) or {}
    if not pdf_path:
        raise ValueError("inputs.pdf_path is required when pdf_to_images is enabled.")

    # Force output to run directory
    output_dir = run_dir / "inputs" / "images"
    _ensure_dir(output_dir)

    # Prefer .venv_pdf for PDF conversion if available, fallback to current interpreter
    if (PROJECT_ROOT / ".venv_pdf/bin/python").exists():
        python_exe = str(PROJECT_ROOT / ".venv_pdf/bin/python")
    else:
        python_exe = sys.executable

    cmd = [
        python_exe,
        "src/pdf_to_images.py",
        "--pdf",
        str(pdf_path),
        "--output-dir",
        str(output_dir),
    ]
    if pdf_opts.get("dpi") is not None:
        cmd += ["--dpi", str(pdf_opts["dpi"])]
    if pdf_opts.get("pages"):
        cmd += ["--pages", str(pdf_opts["pages"])]
    if pdf_opts.get("target_width") is not None:
        cmd += ["--target-width", str(pdf_opts["target_width"])]
    if pdf_opts.get("target_height") is not None:
        cmd += ["--target-height", str(pdf_opts["target_height"])]
    if pdf_opts.get("interpolation"):
        cmd += ["--interpolation", str(pdf_opts["interpolation"])]
    if pdf_opts.get("prefix"):
        cmd += ["--prefix", str(pdf_opts["prefix"])]
    if pdf_opts.get("format"):
        cmd += ["--format", str(pdf_opts["format"])]

    # Always overwrite inside the run directory
    cmd.append("--overwrite")

    if pdf_opts.get("alpha"):
        cmd.append("--alpha")
    return cmd


def _run_command(cmd: List[str], *, dry_run: bool) -> None:
    print(f"Running: {' '.join(cmd)}")
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def _collect_images(config: Dict[str, Any], run_dir: Path) -> List[Path]:
    pdf_opts = _get_nested(config, "inputs", "pdf_to_images", default={}) or {}
    # Use the forced output directory
    output_dir = run_dir / "inputs" / "images"
    image_glob = pdf_opts.get("image_glob", "page_*.png")

    if not output_dir.exists():
        # If PDF conversion didn't run, check config for external source
        external_dir = pdf_opts.get("output_dir")
        if external_dir:
            output_dir = Path(external_dir)
        else:
            raise ValueError("PDF images not found. Enable pdf_to_images or specify output_dir.")

    images = sorted(Path(output_dir).glob(image_glob))
    if not images:
        raise FileNotFoundError(f"No images found in {output_dir} matching {image_glob}")
    return images


def _resolve_page_ids(config: Dict[str, Any], images: List[Path]) -> List[str]:
    prefix = _get_nested(config, "inputs", "pdf_to_images", "prefix", default="page")
    return [f"{prefix}_{index:03d}" for index in range(1, len(images) + 1)]


def _check_and_start_container(container_name: str, dry_run: bool) -> None:
    print(f"Checking container: {container_name}")
    if dry_run:
        return
    # Check if running
    res = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        # Try start
        print(f"Container {container_name} not found or error. Attempting start...")
        subprocess.run(["docker", "start", container_name], check=True)
        time.sleep(2)
        return

    if res.stdout.strip() != "true":
        print(f"Starting container {container_name}...")
        subprocess.run(["docker", "start", container_name], check=True)
        time.sleep(2)
    else:
        print(f"Container {container_name} is running.")


def _run_detection_step(
    config: Dict[str, Any], images: List[Path], page_ids: List[str], run_id: str, *, dry_run: bool
) -> Dict[str, Any]:
    """
    Orchestrates the detection pipeline.
    If running inside a container or configured for in-process, it calls the internal detection logic.
    """
    from src.pipeline.detection import run_detection_step as run_detection_step_internal

    # Simply delegate to the internal implementation which now supports in-process homr
    return run_detection_step_internal(config, images, page_ids, run_id, dry_run=dry_run)


def _resolve_paths_from_detection(
    probe_output_dir: Path, hybrid_output_dir: Path, page_ids: List[str], images: List[Path]
) -> List[Dict[str, str]]:
    """
    Resolves barlines and staff masks from the results of the detection step.

    Barlines: probe_output_dir / <run_id_for_page> / pipeline2_no_peak_filtered_cnn.json
    Staff Mask: hybrid_output_dir / baseline / <stem> / <stem> / <stem>_debug_3_staff.png
    """
    resolved = []

    # We need to find staff masks.
    # The structure in hybrid_output_dir is: baseline / <stem> / <stem> / <stem>_debug_3_staff.png
    # OR sometimes: <hybrid_run>/baseline/<stem>/<stem>/...
    # Let's index them for safety.
    staff_mask_map = {}
    if hybrid_output_dir.exists():
        for p in hybrid_output_dir.rglob("*_debug_3_staff.png"):
            # page_001_debug_3_staff.png -> page_001
            stem = p.name.replace("_debug_3_staff.png", "")
            staff_mask_map[stem] = p

    for page_id, img_path in zip(page_ids, images):
        stem = img_path.stem
        # The run_eval_experiment creates subdirs like: eval2_<ScoreName>_<stem>
        # But if score name inference failed, it might be just eval2_<parent>_<stem>
        # We need to find the directory corresponding to this page in probe_output_dir.

        # Heuristic: look for directory ending with `_{stem}` inside probe_output_dir
        candidate_dirs = list(probe_output_dir.glob(f"*_{stem}"))
        if not candidate_dirs:
            # Fallback check
            candidate_dirs = list(probe_output_dir.glob(f"*{stem}*"))

        barlines_path = None
        if candidate_dirs:
            # Pick the most likely one (exact match suffix preferred)
            # If multiple, take first (or warn)
            target_dir = candidate_dirs[0]
            barlines_path = target_dir / "pipeline2_no_peak_filtered_cnn.json"

        # Fallback to hybrid_results if probe scan didn't run or failed for this page
        if not barlines_path or not barlines_path.exists():
            hybrid_batch_json = hybrid_output_dir / "hybrid_results" / f"{stem}_hybrid.json"
            if hybrid_batch_json.exists():
                barlines_path = hybrid_batch_json

        # Staff Mask
        staff_mask_path = staff_mask_map.get(stem)

        if not barlines_path or not barlines_path.exists():
            # Warning only here, will be caught later if needed
            print(f"Warning: Barlines not found for {page_id} (stem: {stem})")
            barlines_path = Path("MISSING_BARLINES.json")

        if not staff_mask_path or not staff_mask_path.exists():
            print(f"Warning: Staff mask not found for {page_id} (stem: {stem})")
            staff_mask_path = Path("MISSING_STAFF_MASK.png")

        resolved.append(
            {
                "page_id": page_id,
                "page_run": stem,  # Using stem as run identifier local
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )

    return resolved


def _resolve_barlines_and_masks_config(
    config: Dict[str, Any],
    page_ids: List[str],
    page_runs: List[str],
    excluded_page_ids: Optional[set[str]] = None,
) -> List[Dict[str, str]]:
    """Legacy resolution from pre-existing files via config patterns."""
    barlines_root = _get_nested(config, "inputs", "barlines_root")
    barlines_pattern = _get_nested(config, "inputs", "barlines_pattern")
    staff_mask_pattern = _get_nested(config, "inputs", "staff_mask_pattern")
    if not barlines_root or not barlines_pattern or not staff_mask_pattern:
        raise ValueError(
            "barlines_root/barlines_pattern/staff_mask_pattern are required when detection is skipped."
        )
    barlines_root = Path(barlines_root)
    resolved: List[Dict[str, str]] = []
    excluded_page_ids = excluded_page_ids or set()
    for page_id, page_run in zip(page_ids, page_runs):
        barlines_path = barlines_root / barlines_pattern.format(page_run=page_run, page_id=page_id)
        staff_mask_path = barlines_root / staff_mask_pattern.format(
            page_run=page_run, page_id=page_id
        )
        if page_id not in excluded_page_ids:
            if not barlines_path.exists():
                print(f"Warning: Missing barlines JSON: {barlines_path}")
            if not staff_mask_path.exists():
                print(f"Warning: Missing staff mask: {staff_mask_path}")
        resolved.append(
            {
                "page_id": page_id,
                "page_run": page_run,
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )
    return resolved


def _write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))


def _merge_measure_overrides(*overrides_payloads: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: List[Dict[str, Any]] = []
    for payload in overrides_payloads:
        if not payload:
            continue
        items = payload.get("measure_overrides", [])
        if not isinstance(items, list):
            raise ValueError("measure_overrides must be a list.")
        merged.extend(items)
    return {"measure_overrides": merged}


def _get_user_exclude_indices(config: Dict[str, Any]) -> set[int]:
    filters = _get_nested(config, "filters", default={}) or {}
    exclude = filters.get("user_exclude", []) or []
    return {int(x) for x in exclude}


def _normalize_barlines(raw_data: Any) -> List[List[int]]:
    if not raw_data:
        return []
    normalized: List[List[int]] = []
    for item in raw_data:
        if isinstance(item, list) and len(item) == 4:
            normalized.append([int(v) for v in item])
        elif isinstance(item, dict):
            if "barline_location" in item and isinstance(item["barline_location"], list):
                normalized.append([int(v) for v in item["barline_location"]])
            elif all(k in item for k in ("x1", "y1", "x2", "y2")):
                normalized.append(
                    [
                        int(item["x1"]),
                        int(item["y1"]),
                        int(item["x2"]),
                        int(item["y2"]),
                    ]
                )
    return normalized


def _apply_barline_overrides(
    barlines: Sequence[Sequence[int]],
    overrides: Sequence[Dict[str, Any]],
    *,
    page_index: int,
    iou_threshold: float,
    min_width: int,
    x_margin: int,
    y_margin: int,
) -> Tuple[List[List[int]], Dict[str, int]]:
    boxes = [list(map(int, box)) for box in barlines]
    removed_indices: set[int] = set()
    add_count = 0
    remove_requests = 0
    unmatched_remove = 0

    for item in overrides:
        if item.get("page") != page_index:
            continue
        op = item.get("op")
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        bbox = [int(v) for v in bbox]
        if op == "remove":
            remove_requests += 1
            matched = False
            for idx, existing in enumerate(boxes):
                if idx in removed_indices:
                    continue
                iou = barline_iou(
                    tuple(existing),
                    tuple(bbox),
                    min_width=min_width,
                    x_margin=x_margin,
                    y_margin=y_margin,
                )
                if iou >= iou_threshold:
                    removed_indices.add(idx)
                    matched = True
            if not matched:
                unmatched_remove += 1
        elif op == "add":
            boxes.append(bbox)
            add_count += 1

    kept = [box for idx, box in enumerate(boxes) if idx not in removed_indices]
    stats = {
        "removed": len(removed_indices),
        "added": add_count,
        "remove_requests": remove_requests,
        "unmatched_remove": unmatched_remove,
    }
    return kept, stats


def _is_blank_page(
    image_path: Path, config: Dict[str, Any]
) -> Tuple[Optional[bool], Dict[str, float]]:
    blank_cfg = _get_nested(config, "filters", "blank_page_config", default={}) or {}
    pixel_threshold = int(blank_cfg.get("pixel_threshold", 245))
    max_ink_ratio = float(blank_cfg.get("max_ink_ratio", 0.003))
    max_stddev = float(blank_cfg.get("max_stddev", 12.0))

    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None, {}
    ink_ratio = float((image < pixel_threshold).mean())
    stddev = float(image.std())
    is_blank = ink_ratio <= max_ink_ratio and stddev <= max_stddev
    return is_blank, {"ink_ratio": ink_ratio, "stddev": stddev}


def _staff_detect_failed(
    mask_path: Path, config: Dict[str, Any]
) -> Tuple[Optional[bool], Dict[str, float]]:
    staff_cfg = _get_nested(config, "filters", "staff_detect_config", default={}) or {}
    min_nonzero_ratio = float(staff_cfg.get("min_nonzero_ratio", 0.001))
    if not mask_path.exists():
        return None, {"reason": "missing"}
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None, {"reason": "unreadable"}
    nonzero_ratio = float((mask > 0).mean())
    failed = nonzero_ratio < min_nonzero_ratio
    return failed, {"nonzero_ratio": nonzero_ratio}


def _resolve_page_filters(
    config: Dict[str, Any],
    page_ids: Sequence[str],
    images: Sequence[Path],
    resolved: Sequence[Dict[str, str]],
    exclude_indices: set[int],
) -> List[Dict[str, Any]]:
    filters = _get_nested(config, "filters", default={}) or {}

    def _manual_flag(filter_value: Any, page_index: int) -> Optional[bool]:
        if isinstance(filter_value, list):
            return page_index in {int(x) for x in filter_value}
        if isinstance(filter_value, bool):
            return filter_value
        return None

    blank_filter = filters.get("blank_page", "auto")
    staff_filter = filters.get("staff_detect", "auto")
    statuses: List[Dict[str, Any]] = []
    for idx, (page_id, image_path, resolved_item) in enumerate(
        zip(page_ids, images, resolved), start=1
    ):
        blank_manual = _manual_flag(blank_filter, idx)
        if (
            blank_manual is None
            and isinstance(blank_filter, str)
            and blank_filter.lower() == "auto"
        ):
            blank_value, blank_metrics = _is_blank_page(image_path, config)
        else:
            blank_value, blank_metrics = blank_manual, {}

        staff_manual = _manual_flag(staff_filter, idx)
        if (
            staff_manual is None
            and isinstance(staff_filter, str)
            and staff_filter.lower() == "auto"
        ):
            staff_value, staff_metrics = _staff_detect_failed(
                Path(resolved_item["staff_mask"]), config
            )
        else:
            staff_value, staff_metrics = staff_manual, {}

        statuses.append(
            {
                "page_index": idx,
                "page_id": page_id,
                "excluded_by_user": idx in exclude_indices,
                "blank_page": blank_value if blank_value is not None else "unknown",
                "blank_metrics": blank_metrics,
                "staff_detect_failed": staff_value if staff_value is not None else "unknown",
                "staff_metrics": staff_metrics,
            }
        )
    return statuses


def _load_image_size(image_path: Path) -> Tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        return 0, 0
    height, width = image.shape[:2]
    return width, height


def _empty_numbering_payload(page_number: int, image_path: Path) -> Dict[str, Any]:
    width, height = _load_image_size(image_path)
    return {
        "pages": [
            {
                "page_number": page_number,
                "width": width,
                "height": height,
                "systems": [],
            }
        ]
    }


def _build_add_measure_numbers_cmd(
    *,
    barlines: Path,
    staff_mask: Path,
    image: Path,
    output_json: Path,
    page_number: int,
    start_number: int,
    config_path: Optional[Path] = None,
    overlay_path: Optional[Path] = None,
    force_single_system: bool = False,
) -> List[str]:
    cmd = [
        sys.executable,
        "tools/add_measure_numbers.py",
        "--barlines",
        str(barlines),
        "--staff-mask",
        str(staff_mask),
        "--image",
        str(image),
        "--output-json",
        str(output_json),
        "--page-number",
        str(page_number),
        "--start-number",
        str(start_number),
    ]
    if config_path:
        cmd += ["--config", str(config_path)]
    if overlay_path:
        cmd += ["--output-overlay", str(overlay_path)]
    if force_single_system:
        cmd.append("--force-single-system")
    return cmd


def _build_generate_overrides_cmd(
    *,
    numbering_json: Path,
    image: Path,
    output_overrides: Path,
    model_path: Optional[Path],
    enable_rotation_tta: bool,
    debug_image: Optional[Path] = None,
) -> List[str]:
    cmd = [
        sys.executable,
        "tools/generate_numbering_overrides.py",
        "--numbering-json",
        str(numbering_json),
        "--image",
        str(image),
        "--output-overrides",
        str(output_overrides),
    ]
    if model_path:
        cmd += ["--model-path", str(model_path)]
    if debug_image:
        cmd += ["--debug-image", str(debug_image)]
    if enable_rotation_tta:
        cmd.append("--enable-rotation-tta")
    return cmd


def _resolve_page_runs(config: Dict[str, Any], page_ids: List[str]) -> List[str]:
    page_runs = _get_nested(config, "inputs", "page_runs")
    if page_runs and isinstance(page_runs, list):
        # Explicit page runs
        if len(page_runs) != len(page_ids):
            raise ValueError("inputs.page_runs length must match number of pages.")
        return [str(item) for item in page_runs]

    # Infer if not provided (safe defaults)
    return page_ids


def _build_manifest(
    config: Dict[str, Any],
    *,
    run_id: str,
    run_dir: Path,
    images: List[Path],
    page_ids: List[str],
    page_runs: List[str],
    resolved: List[Dict[str, str]],
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to YAML config.")
    parser.add_argument("--run-id", type=str, help="Override run_id from config.")
    parser.add_argument("--output-root", type=Path, help="Override output root from config.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Resolve inputs and filters, write manifest/filters.json, skip numbering.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = _load_yaml(args.config)
    run_id = args.run_id or _get_nested(config, "run", "run_id")
    if not run_id:
        run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_root or _get_nested(
        config, "run", "output_root", default="logs/full_pipeline_runs"
    )
    run_dir = Path(output_root) / run_id
    inputs_dir = run_dir / "inputs"
    intermediate_dir = run_dir / "intermediate"
    outputs_dir = run_dir / "outputs"
    for directory in (inputs_dir, intermediate_dir, outputs_dir):
        _ensure_dir(directory)

    commands: List[List[str]] = []

    # --- Step 1: PDF to Images ---
    if _get_nested(config, "steps", "pdf_to_images", default=False):
        pdf_cmd = _build_pdf_command(config, run_dir)
        commands.append(pdf_cmd)
        _run_command(pdf_cmd, dry_run=args.dry_run)

    images = _collect_images(config, run_dir)
    page_ids = _resolve_page_ids(config, images)

    # --- Step 2: Detection ---
    run_detection = _get_nested(config, "steps", "detection", default=False)
    probe_output_dir = None
    hybrid_output_dir = None

    if run_detection:
        det_result = _run_detection_step(config, images, page_ids, run_id, dry_run=args.dry_run)
        commands.extend(det_result["commands"])
        probe_output_dir = det_result["probe_output_dir"]
        hybrid_output_dir = det_result["hybrid_output_dir"]

    # Resolve Inputs for Numbering
    # If detection ran, resolve from there. Else resolve from config patterns (legacy/cache).

    excluded_indices = _get_user_exclude_indices(config)
    excluded_page_ids = {page_ids[idx - 1] for idx in excluded_indices if 1 <= idx <= len(page_ids)}

    if run_detection and probe_output_dir and hybrid_output_dir:
        resolved = _resolve_paths_from_detection(
            probe_output_dir, hybrid_output_dir, page_ids, images
        )
        page_runs = page_ids  # Local run assumption
    else:
        page_runs = _resolve_page_runs(config, page_ids)
        resolved = _resolve_barlines_and_masks_config(
            config, page_ids, page_runs, excluded_page_ids=excluded_page_ids
        )

    page_statuses = _resolve_page_filters(config, page_ids, images, resolved, excluded_indices)

    apply_barlines = _get_nested(config, "steps", "apply_barline_overrides", default=False)
    user_overrides_path = _get_nested(config, "inputs", "measure_overrides")
    barline_overrides_path = _get_nested(config, "inputs", "barline_overrides")
    barline_override_payload = None
    if barline_overrides_path:
        barline_override_payload = _load_json(Path(barline_overrides_path))
    barline_override_cfg = (
        _get_nested(config, "inputs", "barline_overrides_config", default={}) or {}
    )
    barline_iou_threshold = float(barline_override_cfg.get("iou_threshold", 0.5))
    barline_min_width = int(barline_override_cfg.get("min_width", BARLINE_DEFAULT_MIN_WIDTH))
    barline_x_margin = int(barline_override_cfg.get("x_margin", BARLINE_X_MARGIN))
    barline_y_margin = int(barline_override_cfg.get("y_margin", BARLINE_Y_MARGIN))
    user_overrides_payload = None
    if user_overrides_path:
        user_overrides_payload = _load_json(Path(user_overrides_path))

    force_single_system = bool(
        _get_nested(config, "numbering", "force_single_system", default=False)
    )
    enable_rotation_tta = bool(_get_nested(config, "mmr", "enable_rotation_tta", default=False))
    model_path = _get_nested(config, "mmr", "model_path")
    model_path = Path(model_path) if model_path else None
    debug_root = _get_nested(config, "mmr", "debug_root")
    debug_root = Path(debug_root) if debug_root else None

    step_numbering = _get_nested(config, "steps", "numbering_base", default=False)
    step_mmr = _get_nested(config, "steps", "mmr_overrides", default=False)
    step_apply = _get_nested(config, "steps", "apply_measure_overrides", default=False)
    step_overlay = _get_nested(config, "steps", "overlay", default=False)

    if not args.validate_only:
        if (step_mmr or step_apply or step_overlay) and not step_numbering:
            raise ValueError("numbering_base must be enabled before MMR or final numbering steps.")

    numbering_base_paths: List[Path] = []
    numbering_final_paths: List[Path] = []
    barline_override_stats: Dict[str, Dict[str, int]] = {}

    for index, (page_id, image_path, resolved_item) in enumerate(
        zip(page_ids, images, resolved), start=1
    ):
        page_intermediate = intermediate_dir / page_id
        page_outputs = outputs_dir / page_id
        _ensure_dir(page_intermediate)
        _ensure_dir(page_outputs)

        if page_id in excluded_page_ids:
            empty_base = page_intermediate / "numbering_base.json"
            numbering_base_paths.append(empty_base)
            if not args.dry_run:
                _write_json(empty_base, _empty_numbering_payload(index, image_path))

            if (step_apply or step_overlay) and not args.validate_only:
                empty_final = page_outputs / "numbering_final.json"
                numbering_final_paths.append(empty_final)
                if not args.dry_run:
                    _write_json(empty_final, _empty_numbering_payload(index, image_path))
            barline_override_stats[page_id] = {
                "removed": 0,
                "added": 0,
                "remove_requests": 0,
                "unmatched_remove": 0,
            }
            continue

        barlines_path = Path(resolved_item["barlines_json"])
        if apply_barlines:
            corrected_path = page_intermediate / "barlines_corrected.json"
            if barline_override_payload and isinstance(
                barline_override_payload.get("barline_overrides", []), list
            ):
                raw_barlines = _load_json(barlines_path)
                barlines_list = _normalize_barlines(raw_barlines)
                corrected, stats = _apply_barline_overrides(
                    barlines_list,
                    barline_override_payload.get("barline_overrides", []),
                    page_index=index - 1,
                    iou_threshold=barline_iou_threshold,
                    min_width=barline_min_width,
                    x_margin=barline_x_margin,
                    y_margin=barline_y_margin,
                )
                barline_override_stats[page_id] = stats
                if not args.dry_run:
                    _write_json(corrected_path, corrected)
            else:
                if not args.dry_run and barlines_path.exists():
                    corrected_path.write_text(barlines_path.read_text())
                barline_override_stats[page_id] = {
                    "removed": 0,
                    "added": 0,
                    "remove_requests": 0,
                    "unmatched_remove": 0,
                }
            barlines_path = corrected_path
        else:
            barline_override_stats[page_id] = {
                "removed": 0,
                "added": 0,
                "remove_requests": 0,
                "unmatched_remove": 0,
            }

        numbering_base = page_intermediate / "numbering_base.json"
        numbering_base_paths.append(numbering_base)
        cmd_base = _build_add_measure_numbers_cmd(
            barlines=barlines_path,
            staff_mask=Path(resolved_item["staff_mask"]),
            image=image_path,
            output_json=numbering_base,
            page_number=index,
            start_number=1,
            force_single_system=force_single_system,
        )
        commands.append(cmd_base)
        if step_numbering and not args.validate_only:
            _run_command(cmd_base, dry_run=args.dry_run)

        mmr_overrides_payload = None
        if step_mmr and not args.validate_only:
            overrides_mmr = page_intermediate / "overrides_mmr.json"
            cmd_mmr = _build_generate_overrides_cmd(
                numbering_json=numbering_base,
                image=image_path,
                output_overrides=overrides_mmr,
                model_path=model_path,
                enable_rotation_tta=enable_rotation_tta,
                debug_image=(debug_root / f"{page_id}_mmr_debug.png") if debug_root else None,
            )
            commands.append(cmd_mmr)
            _run_command(cmd_mmr, dry_run=args.dry_run)
            if not args.dry_run:
                mmr_overrides_payload = _load_json(overrides_mmr)

        if (step_apply or step_overlay) and not args.validate_only:
            overrides_payload = _merge_measure_overrides(
                mmr_overrides_payload, user_overrides_payload
            )
            combined_path = page_intermediate / "overrides_combined.json"
            if not args.dry_run:
                _write_json(combined_path, overrides_payload)
            final_json = page_outputs / "numbering_final.json"
            numbering_final_paths.append(final_json)
            overlay_path = page_outputs / "numbering_overlay.png" if step_overlay else None
            cmd_final = _build_add_measure_numbers_cmd(
                barlines=barlines_path,
                staff_mask=Path(resolved_item["staff_mask"]),
                image=image_path,
                output_json=final_json,
                page_number=index,
                start_number=1,
                config_path=combined_path,
                overlay_path=overlay_path,
                force_single_system=force_single_system,
            )
            commands.append(cmd_final)
            _run_command(cmd_final, dry_run=args.dry_run)

    if len(numbering_base_paths) > 1 and not args.dry_run and not args.validate_only:
        combined_base = {
            "pages": [page for path in numbering_base_paths for page in _load_json(path)["pages"]]
        }
        _write_json(intermediate_dir / "numbering_base.json", combined_base)
    if len(numbering_final_paths) > 1 and not args.dry_run and not args.validate_only:
        combined_final = {
            "pages": [page for path in numbering_final_paths for page in _load_json(path)["pages"]]
        }
        _write_json(outputs_dir / "numbering_final.json", combined_final)

    if not args.dry_run:
        _write_json(run_dir / "filters.json", {"pages": page_statuses})

    manifest = _build_manifest(
        config,
        run_id=run_id,
        run_dir=run_dir,
        images=images,
        page_ids=page_ids,
        page_runs=page_runs,  # Now may be just page_ids
        resolved=resolved,
        commands=commands,
        page_statuses=page_statuses,
        barline_override_stats=barline_override_stats,
    )
    _write_manifest(run_dir / "manifest.json", manifest)
    print(f"Wrote manifest to {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
