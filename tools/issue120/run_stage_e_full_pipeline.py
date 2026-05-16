import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from src.pipeline.core.config import load_yaml
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
        
    inv = json.loads(args.inventory.read_text())
    
    exclude_list = []
    if args.exclude.exists():
        exclude_list = json.loads(args.exclude.read_text()).get("excluded_pages", [])
        
    image_paths = []
    for rec in inv.get("records", []):
        score = rec["score"]
        page = rec["page"]
        if {"score": score, "page": page} in exclude_list:
            continue
        image_paths.append(Path(rec["image"]))
        
    if len(image_paths) != 68:
        logger.error(f"Expected 68 images, got {len(image_paths)}")
        sys.exit(1)
        
    # Prepare a dedicated image directory for the pipeline to glob
    stage_e_images_dir = args.output_root / "stage_e_full_pipeline" / "images"
    stage_e_images_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Copying {len(image_paths)} images to {stage_e_images_dir}...")
    for img_path in image_paths:
        dest_path = stage_e_images_dir / f"{img_path.parent.name}_{img_path.name}"
        if not dest_path.exists():
            shutil.copy2(img_path, dest_path)
            
    # Load config and override input directory
    config = load_yaml(args.config)
    if "inputs" not in config:
        config["inputs"] = {}
    if "pdf_to_images" not in config["inputs"]:
        config["inputs"]["pdf_to_images"] = {}
        
    config["inputs"]["pdf_to_images"]["output_dir"] = str(stage_e_images_dir)
    config["inputs"]["pdf_to_images"]["image_glob"] = "*.png"
    config["run"]["run_id"] = "stage_e_full_pipeline"
    
    # Save a temporary config
    temp_config_path = args.output_root / "stage_e_full_pipeline" / "stage_e_config.yaml"
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
