import argparse
import logging
import shutil
import sys
from pathlib import Path

from src.pipeline.core.config import load_yaml
from src.pipeline.detector_routes.stage_e_dense_full_pipeline import (
    apply_stage_e_dense_patch,
    reconstruct_stage_e_dense_route,
)
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run Stage E full 68-page pipeline.")
    parser.add_argument("--config", type=Path, default="configs/issue120_stage_e_full_pipeline.yaml")
    parser.add_argument("--inventory", type=Path, default="logs/issue36_prep/20260208_bench_inventory.json")
    parser.add_argument("--exclude", type=Path, default="logs/issue36_prep/excluded_pages_for_gt_prep.json")
    parser.add_argument("--output-root", type=Path, default="logs/issue120_e2e_recovery")
    args = parser.parse_args()

    if not args.inventory.exists():
        logger.error(f"Inventory not found: {args.inventory}")
        sys.exit(1)
    if not args.exclude.exists():
        logger.error(f"Exclude file not found: {args.exclude}")
        sys.exit(1)

    stage_e_root = args.output_root / "stage_e_full_pipeline"
    if stage_e_root.exists():
        logger.info("Removing stale Stage E run directory: %s", stage_e_root)
        shutil.rmtree(stage_e_root)
    stage_e_root.mkdir(parents=True, exist_ok=True)

    route_artifacts = reconstruct_stage_e_dense_route(
        inventory=args.inventory,
        exclude=args.exclude,
        stage_e_root=stage_e_root,
    )

    stage_e_images_dir = stage_e_root / "images"
    stage_e_images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Copying {len(route_artifacts.image_paths)} images to {stage_e_images_dir}...")
    for img_path in route_artifacts.image_paths:
        dest_path = stage_e_images_dir / f"{img_path.parent.name}_{img_path.name}"
        shutil.copy2(img_path, dest_path)

    config = load_yaml(args.config)
    if "inputs" not in config:
        config["inputs"] = {}
    if "pdf_to_images" not in config["inputs"]:
        config["inputs"]["pdf_to_images"] = {}
    if "detection" not in config:
        config["detection"] = {}

    config["inputs"]["pdf_to_images"]["output_dir"] = str(stage_e_images_dir)
    config["inputs"]["pdf_to_images"]["image_glob"] = "*.png"
    config["run"]["run_id"] = "stage_e_full_pipeline"
    config["detection"]["stage_e_dense_reconstruction_root"] = str(route_artifacts.filtered_root)
    config["detection"]["stage_e_issue53_candidates_root"] = str(route_artifacts.issue53_root)
    config["detection"]["probe_use_original_images"] = True

    apply_stage_e_dense_patch(
        issue53_root=route_artifacts.issue53_root,
        filtered_root=route_artifacts.filtered_root,
    )

    temp_config_path = stage_e_root / "stage_e_config.yaml"
    import yaml

    with open(temp_config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    logger.info(f"Starting pipeline using config: {temp_config_path}")

    run_pipeline(
        config_path=temp_config_path,
        run_id="stage_e_full_pipeline",
        output_root=args.output_root,
    )

    logger.info("Stage E full pipeline run completed.")


if __name__ == "__main__":
    main()
