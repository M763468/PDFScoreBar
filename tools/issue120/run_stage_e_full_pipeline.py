import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from src.pipeline.core.config import load_yaml
from src.pipeline.detector_routes.dense_full_pipeline import reconstruct_dense_full_pipeline_route
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run Stage E full 68-page pipeline.")
    parser.add_argument("--config", type=Path, default="configs/issue120_stage_e_full_pipeline.yaml")
    parser.add_argument("--inventory", type=Path, default="logs/issue36_prep/20260208_bench_inventory.json")
    parser.add_argument("--exclude", type=Path, default="logs/issue36_prep/excluded_pages_for_gt_prep.json")
    parser.add_argument("--output-root", type=Path, default="logs/issue120_e2e_recovery")
    parser.add_argument(
        "--dense-route-verbose-logs",
        action="store_true",
        help="Write full subprocess logs for dense-route reconstruction. Defaults to compact bounded logs.",
    )
    args = parser.parse_args()

    if not args.inventory.exists():
        logger.error(f"Inventory not found: {args.inventory}")
        sys.exit(1)
    if not args.exclude.exists():
        logger.error(f"Exclude file not found: {args.exclude}")
        sys.exit(1)

    route_root = args.output_root / "stage_e_full_pipeline"
    if route_root.exists():
        logger.info("Removing stale Stage E run directory: %s", route_root)
        shutil.rmtree(route_root)
    route_root.mkdir(parents=True, exist_ok=True)

    run_started_at = time.perf_counter()
    route_artifacts = reconstruct_dense_full_pipeline_route(
        inventory=args.inventory,
        exclude=args.exclude,
        route_root=route_root,
        verbose_logs=args.dense_route_verbose_logs,
    )

    route_images_dir = route_root / "images"
    route_images_dir.mkdir(parents=True, exist_ok=True)

    image_copy_started_at = time.perf_counter()
    logger.info(f"Copying {len(route_artifacts.image_paths)} images to {route_images_dir}...")
    for img_path in route_artifacts.image_paths:
        dest_path = route_images_dir / f"{img_path.parent.name}_{img_path.name}"
        shutil.copy2(img_path, dest_path)
    image_copy_duration_sec = time.perf_counter() - image_copy_started_at

    config = load_yaml(args.config)
    if "inputs" not in config:
        config["inputs"] = {}
    if "pdf_to_images" not in config["inputs"]:
        config["inputs"]["pdf_to_images"] = {}
    if "detection" not in config:
        config["detection"] = {}

    config["inputs"]["pdf_to_images"]["output_dir"] = str(route_images_dir)
    config["inputs"]["pdf_to_images"]["image_glob"] = "*.png"
    config["run"]["run_id"] = "stage_e_full_pipeline"
    config["detection"]["precomputed_probe_candidates_root"] = str(route_artifacts.probe_rescue_root)
    config["detection"]["cnn_bands_from"] = str(route_artifacts.filtered_root)
    config["detection"]["probe_use_original_images"] = True

    temp_config_path = route_root / "stage_e_config.yaml"
    import yaml

    with open(temp_config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    logger.info(f"Starting pipeline using config: {temp_config_path}")

    pipeline_started_at = time.perf_counter()
    run_pipeline(
        config_path=temp_config_path,
        run_id="stage_e_full_pipeline",
        output_root=args.output_root,
    )
    pipeline_duration_sec = time.perf_counter() - pipeline_started_at

    run_summary_path = route_root / "stage_e_runtime_summary.json"
    run_summary = {
        "schema_version": "tools.issue120.stage_e_full_pipeline.runtime_summary.v1",
        "total_duration_sec": time.perf_counter() - run_started_at,
        "dense_route_execution_summary": route_artifacts.execution_summary,
        "image_copy": {
            "duration_sec": image_copy_duration_sec,
            "image_count": len(route_artifacts.image_paths),
            "output_dir": str(route_images_dir),
        },
        "pipeline": {
            "duration_sec": pipeline_duration_sec,
            "config_path": str(temp_config_path),
            "run_id": "stage_e_full_pipeline",
            "output_root": str(args.output_root),
        },
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Stage E runtime summary written to %s", run_summary_path)
    logger.info("Stage E full pipeline run completed.")


if __name__ == "__main__":
    main()
