"""Detection step orchestration."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.config import get_nested
from src.pipeline.io import ensure_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def check_and_start_container(container_name: str, dry_run: bool) -> None:
    print(f"Checking container: {container_name}")
    if dry_run:
        return
    res = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
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


def run_detection_step(
    config: Dict[str, Any],
    images: List[Path],
    page_ids: List[str],
    run_id: str,
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run hybrid detection -> probe scan -> CNN scoring."""
    det_cfg = get_nested(config, "detection", default={}) or {}
    container_name = det_cfg.get("container_name", "sr_eval_gpu_exp")
    hybrid_root = Path(det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))

    # TODO: Provide a native Python API instead of docker subprocess calls.
    check_and_start_container(container_name, dry_run)

    hybrid_run_id = run_id
    hybrid_output_dir = hybrid_root / hybrid_run_id

    commands: List[List[str]] = []

    print("--- Step 2.1: Hybrid Detection Batch (Docker) ---")

    container_images = []
    for img_path in images:
        try:
            rel_img = img_path.resolve().relative_to(PROJECT_ROOT.resolve())
            container_images.append(f"/workspace/{rel_img}")
        except ValueError:
            container_images.append(str(img_path.resolve()))

    batch_script = "/workspace/tools/run_hybrid_batch.py"
    cmd_batch = [
        "docker",
        "exec",
        container_name,
        "bash",
        "-lc",
        f"python3 {batch_script} --images {' '.join(container_images)} --run-id {hybrid_run_id} --output-root /workspace/{hybrid_root}",
    ]

    print(f"Running Batch Detection: {' '.join(cmd_batch)}")
    if not dry_run:
        subprocess.run(cmd_batch, check=True)
    commands.append(cmd_batch)

    print("--- Step 2.2: Probe Scan (Host) ---")
    probe_output_root = Path(f"logs/full_pipeline_runs/{run_id}/intermediate/probe_scan")
    ensure_dir(probe_output_root)

    image_root = get_nested(config, "inputs", "pdf_to_images", "output_dir")

    cmd_probe = [
        sys.executable,
        "tools/run_eval_experiment.py",
        "--image-root",
        str(image_root),
        "--output-root",
        str(probe_output_root),
        "--bands-from",
        str(hybrid_output_dir),
        "--staff-mask-dir",
        str(hybrid_output_dir),
        "--ink-threshold",
        str(det_cfg.get("ink_threshold", 230)),
        "--min-ratio",
        str(det_cfg.get("min_ratio", 0.70)),
        "--min-height-ratio",
        str(det_cfg.get("min_height_ratio", 0.012)),
    ]
    if det_cfg.get("min_width_ratio") is not None:
        cmd_probe += ["--min-width-ratio", str(det_cfg.get("min_width_ratio"))]
    if det_cfg.get("probe_row_filter_mode"):
        cmd_probe += ["--probe-row-filter-mode", str(det_cfg.get("probe_row_filter_mode"))]
    if det_cfg.get("probe_endpoint_x_scale") is not None:
        cmd_probe += ["--probe-endpoint-x-scale", str(det_cfg.get("probe_endpoint_x_scale"))]
    if det_cfg.get("probe_endpoint_y_scale") is not None:
        cmd_probe += ["--probe-endpoint-y-scale", str(det_cfg.get("probe_endpoint_y_scale"))]
    if det_cfg.get("probe_score_name"):
        cmd_probe += ["--score-name", str(det_cfg.get("probe_score_name"))]

    if det_cfg.get("probe_skip_existing"):
        cmd_probe.append("--skip-existing")

    subprocess.run(cmd_probe, check=not dry_run)
    commands.append(cmd_probe)

    print("--- Step 2.3: CNN Scoring (Host) ---")
    cnn_model = det_cfg.get("cnn_model_path")
    if not cnn_model:
        raise ValueError("detection.cnn_model_path is required.")

    cmd_score = [
        sys.executable,
        "tools/cnn_classifier/score_candidates_batch.py",
        "--logs",
        str(probe_output_root),
        "--model",
        str(cnn_model),
        "--threshold",
        str(det_cfg.get("cnn_threshold", 0.1)),
    ]
    subprocess.run(cmd_score, check=not dry_run)
    commands.append(cmd_score)

    return {
        "commands": commands,
        "hybrid_output_dir": hybrid_output_dir,
        "probe_output_dir": probe_output_root,
    }


def resolve_paths_from_detection(
    probe_output_dir: Path, hybrid_output_dir: Path, page_ids: List[str], images: List[Path]
) -> List[Dict[str, str]]:
    resolved: List[Dict[str, str]] = []

    staff_mask_map: Dict[str, Path] = {}
    if hybrid_output_dir.exists():
        for path in hybrid_output_dir.rglob("*_debug_3_staff.png"):
            stem = path.name.replace("_debug_3_staff.png", "")
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
            print(f"Warning: Barlines not found for {page_id} (stem: {stem})")
            barlines_path = Path("MISSING_BARLINES.json")

        if not staff_mask_path or not staff_mask_path.exists():
            print(f"Warning: Staff mask not found for {page_id} (stem: {stem})")
            staff_mask_path = Path("MISSING_STAFF_MASK.png")

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
