import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from src.pipeline.core.config import load_yaml
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

GENERATION_PARAMS = {
    "band_source": "row_stats",
    "band_cluster_max_dist": "25.0",
    "ink_threshold": "240",
    "min_ratio": "0.6",
    "min_height_ratio": "0.006",
    "min_width_ratio": "0.0",
    "probe_width": "4",
    "max_per_band": "80",
    "band_scan_line_ratio": "0.6",
    "band_scan_min_lines": "5",
}

FILTER_PARAMS = {
    "left_margin_ratio": "0.12",
    "clef_left_ratio": "0.25",
    "min_height_median_ratio": "0.6",
    "ink_threshold": "180",
    "min_ink_ratio": "0.18",
    "paper_threshold": "200",
    "min_paper_overlap_ratio": "0.6",
    "min_staff_overlap_ratio": "0.02",
}


def _add_params(cmd: list[str], params: dict[str, str]) -> None:
    for key, value in params.items():
        cmd.extend([f"--{key.replace('_', '-')}", value])


def _run_command(cmd: list[str], *, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("+ %s > %s", " ".join(cmd), log_path)
    with log_path.open("w", encoding="utf-8") as log_file:
        subprocess.run(cmd, check=True, stdout=log_file, stderr=subprocess.STDOUT)


def regenerate_dense_candidates(*, inventory: Path, exclude: Path, stage_e_root: Path) -> Path:
    """Regenerate the recovered dense candidate/filter root inside this Stage E run."""
    dense_root = stage_e_root / "dense_candidate_reconstruction"
    raw_root = dense_root / "probe_candidates_from_inventory"
    filtered_root = dense_root / "probe_candidates_filtered"
    suggestions_root = dense_root / "filter_suggestions"
    generation_summary = dense_root / "probe_generation_summary.json"
    filter_summary = dense_root / "filter_apply_summary.json"
    log_dir = dense_root / "logs"

    if dense_root.exists():
        shutil.rmtree(dense_root)
    dense_root.mkdir(parents=True, exist_ok=True)

    gen_cmd = [
        sys.executable,
        "tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py",
        "--inventory",
        str(inventory),
        "--exclude",
        str(exclude),
        "--output-root",
        str(raw_root),
        "--summary-out",
        str(generation_summary),
    ]
    _add_params(gen_cmd, GENERATION_PARAMS)
    _run_command(gen_cmd, log_path=log_dir / "01_generate_probe_candidates.log")

    filter_cmd = [
        sys.executable,
        "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py",
        "--inventory",
        str(inventory),
        "--exclude",
        str(exclude),
        "--candidates-root",
        str(raw_root),
        "--output-root",
        str(filtered_root),
        "--suggestions-root",
        str(suggestions_root),
        "--summary-out",
        str(filter_summary),
    ]
    _add_params(filter_cmd, FILTER_PARAMS)
    _run_command(filter_cmd, log_path=log_dir / "02_apply_candidate_filter.log")

    summary = json.loads(filter_summary.read_text())
    if summary.get("processed") != 68 or summary.get("errors") != 0:
        raise RuntimeError(
            "Dense candidate reconstruction did not complete cleanly: "
            f"processed={summary.get('processed')} errors={summary.get('errors')}"
        )
    return filtered_root


def regenerate_issue53_candidates(*, image_paths: list[Path], filtered_root: Path, stage_e_root: Path) -> Path:
    """Regenerate the Issue53-style probe rescue root used by the dense route."""
    from src.pipeline.steps.probe_scan import run_probe_scan_batch

    issue53_root = stage_e_root / "dense_candidate_reconstruction" / "issue53_probe_rescue_candidates"
    shutil.rmtree(issue53_root, ignore_errors=True)
    issue53_root.mkdir(parents=True, exist_ok=True)

    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }
    processed = run_probe_scan_batch(
        images=image_paths,
        output_root=issue53_root,
        bands_from=filtered_root,
        staff_mask_dir=None,
        clef_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        detect_probe_kwargs=detect_probe_kwargs,
        enable_heuristic_filters=False,
    )
    if processed != 68:
        raise RuntimeError(f"Issue53 candidate reconstruction processed {processed}/68 pages")
    return issue53_root


def _load_json_boxes(path: Path):
    payload = json.loads(path.read_text())
    boxes = []
    if not isinstance(payload, list):
        return boxes
    for item in payload:
        if isinstance(item, dict) and "bbox" in item:
            item = item["bbox"]
        if isinstance(item, list) and len(item) >= 4:
            boxes.append(tuple(int(round(float(v))) for v in item[:4]))
    return boxes


def _split_score_page_from_stem(stem: str):
    marker = "_page_"
    idx = stem.rfind(marker)
    if idx < 0:
        return None
    score = stem[:idx]
    page = f"page_{stem[idx + len(marker):]}"
    return score, page


def patch_dense_bands_loader() -> None:
    """Resolve fresh Stage E dense roots for composite stems like Score_page_001."""
    from src.pipeline.steps import cnn_scoring, probe_scan

    original_loader = probe_scan._load_bands_for_image
    if getattr(original_loader, "_stage_e_dense_loader", False):
        return

    def patched_loader(*, bands_from, current_score_name, stem):
        if bands_from:
            root = Path(bands_from)
            split = _split_score_page_from_stem(stem)
            if split is not None:
                score, page = split
                for candidate in [
                    root / score / page / "pipeline2_no_peak_candidates.json",
                    root / score / page / "pipeline2_no_peak_scored.json",
                ]:
                    if candidate.exists():
                        return _load_json_boxes(candidate)
        return original_loader(
            bands_from=bands_from,
            current_score_name=current_score_name,
            stem=stem,
        )

    patched_loader._stage_e_dense_loader = True
    probe_scan._load_bands_for_image = patched_loader
    cnn_scoring._load_bands_for_image = patched_loader


def patch_detector_for_stage_e(*, issue53_root: Path, filtered_root: Path) -> None:
    """Connect reconstructed Issue53 candidates to the full pipeline detector step."""
    import src.pipeline.detection.orchestrator as detection_orchestrator
    from src.pipeline.core.run_ids import build_probe_run_id
    from src.pipeline.utils.io import ensure_dir
    from src.pipeline.detection.orchestrator import DetectorOrchestrator

    if getattr(detection_orchestrator, "_stage_e_issue53_patch", False):
        return

    original_cnn_batch = detection_orchestrator.run_cnn_scoring_batch
    original_get_images = DetectorOrchestrator._get_effective_images_for_probe

    def get_effective_images_for_probe(self):
        if bool(self.det_cfg.get("probe_use_original_images", False)):
            return self.images, 1
        return original_get_images(self)

    def copy_issue53_candidates(**kwargs):
        images = list(kwargs["images"])
        output_root = Path(kwargs["output_root"])
        score_name = kwargs.get("score_name")
        processed = 0
        for img_path in images:
            split = _split_score_page_from_stem(img_path.stem)
            if split is None:
                raise RuntimeError(f"Cannot map Stage E image stem to score/page: {img_path.stem}")
            score, page = split
            src = issue53_root / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json"
            if not src.exists():
                raise FileNotFoundError(f"Missing reconstructed Issue53 candidates: {src}")
            dest_dir = output_root / build_probe_run_id(img_path, score_name=score_name)
            ensure_dir(dest_dir)
            shutil.copy2(src, dest_dir / "pipeline2_no_peak_candidates.json")
            processed += 1
        return processed

    def run_cnn_scoring_batch_with_dense_bands(**kwargs):
        kwargs["bands_from"] = filtered_root
        return original_cnn_batch(**kwargs)

    DetectorOrchestrator._get_effective_images_for_probe = get_effective_images_for_probe
    detection_orchestrator.run_probe_scan_batch = copy_issue53_candidates
    detection_orchestrator.run_cnn_scoring_batch = run_cnn_scoring_batch_with_dense_bands
    detection_orchestrator._stage_e_issue53_patch = True


def apply_stage_e_dense_patch(*, issue53_root: Path, filtered_root: Path) -> None:
    patch_dense_bands_loader()
    patch_detector_for_stage_e(issue53_root=issue53_root, filtered_root=filtered_root)
    logger.info("Applied Issue #141 Stage E Issue53 candidate reconstruction patch.")


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

    stage_e_root = args.output_root / "stage_e_full_pipeline"
    filtered_root = regenerate_dense_candidates(
        inventory=args.inventory,
        exclude=args.exclude,
        stage_e_root=stage_e_root,
    )
    issue53_root = regenerate_issue53_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        stage_e_root=stage_e_root,
    )

    stage_e_images_dir = stage_e_root / "images"
    stage_e_images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Copying {len(image_paths)} images to {stage_e_images_dir}...")
    for img_path in image_paths:
        dest_path = stage_e_images_dir / f"{img_path.parent.name}_{img_path.name}"
        if not dest_path.exists():
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
    config["detection"]["stage_e_dense_reconstruction_root"] = str(filtered_root)
    config["detection"]["stage_e_issue53_candidates_root"] = str(issue53_root)
    config["detection"]["probe_use_original_images"] = True

    apply_stage_e_dense_patch(issue53_root=issue53_root, filtered_root=filtered_root)

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
