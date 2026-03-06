"""End-to-end pipeline entrypoint (no CLI wrapper)."""

from __future__ import annotations

import datetime as dt
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from src.common.barline_evaluation import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
)
from src.pipeline.barlines import (
    apply_barline_overrides,
    merge_measure_overrides,
    normalize_barlines,
)
from src.pipeline.config import get_nested, load_yaml
from src.pipeline.detection import (
    resolve_barlines_and_masks_config,
    resolve_paths_from_detection,
    run_detection_step,
)
from src.pipeline.filters import get_user_exclude_indices, resolve_page_filters
from src.pipeline.images import collect_images, resolve_page_ids
from src.pipeline.io import ensure_dir, load_json, write_json, write_manifest
from src.pipeline.manifest import build_manifest
from src.pipeline.numbering import (
    build_add_measure_numbers_cmd,
    build_generate_overrides_cmd,
    empty_numbering_payload,
)
from src.pipeline.python_env import get_pipeline_python

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _build_pdf_command(config: Dict[str, Any], run_dir: Path) -> List[str]:
    pdf_path = get_nested(config, "inputs", "pdf_path")
    pdf_opts = get_nested(config, "inputs", "pdf_to_images", default={}) or {}
    if not pdf_path:
        raise ValueError("inputs.pdf_path is required when pdf_to_images is enabled.")

    output_dir = run_dir / "inputs" / "images"
    ensure_dir(output_dir)

    python_cmd = get_pipeline_python("pdf_to_images")

    cmd = python_cmd + [
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

    cmd.append("--overwrite")

    if pdf_opts.get("alpha"):
        cmd.append("--alpha")
    return cmd


def _run_command(cmd: List[str], *, dry_run: bool) -> None:
    cmd_str = " ".join(cmd)
    logger.info(f"Executing: {cmd_str}")
    if dry_run:
        return
    
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as p:
        if p.stdout:
            for line in p.stdout:
                line = line.rstrip("\n")
                logger.info(f"|> {line}")
        p.wait()
        if p.returncode != 0:
            logger.error(f"Command failed with exit code {p.returncode}: {cmd_str}")
            raise subprocess.CalledProcessError(p.returncode, cmd)
    logger.info(f"Successfully executed: {cmd[0]} (exit code 0)")


def _resolve_page_runs(config: Dict[str, Any], page_ids: List[str]) -> List[str]:
    page_runs = get_nested(config, "inputs", "page_runs")
    if page_runs and isinstance(page_runs, list):
        if len(page_runs) != len(page_ids):
            raise ValueError("inputs.page_runs length must match number of pages.")
        return [str(item) for item in page_runs]
    return page_ids


def run_pipeline(
    config_path: Path,
    *,
    run_id: Optional[str] = None,
    output_root: Optional[Path] = None,
    dry_run: bool = False,
    validate_only: bool = False,
    skip_existing: bool = False,
    page_limit: Optional[int] = None,
) -> Path:
    config = load_yaml(config_path)
    run_id_value = run_id or get_nested(config, "run", "run_id")
    if not run_id_value:
        run_id_value = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    output_root_value = output_root or get_nested(
        config, "run", "output_root", default="logs/full_pipeline_runs"
    )
    run_dir = Path(output_root_value) / run_id_value

    # TODO: Centralize log directory naming with logs/README.md categories.
    inputs_dir = run_dir / "inputs"
    intermediate_dir = run_dir / "intermediate"
    outputs_dir = run_dir / "outputs"
    for directory in (inputs_dir, intermediate_dir, outputs_dir):
        ensure_dir(directory)

    commands: List[List[str]] = []

    if get_nested(config, "steps", "pdf_to_images", default=False):
        if (
            skip_existing
            and (run_dir / "inputs" / "images").exists()
            and list((run_dir / "inputs" / "images").glob("*.png"))
        ):
            logger.info("Skipping pdf_to_images: output directory exists and is not empty.")
        else:
            pdf_cmd = _build_pdf_command(config, run_dir)
            commands.append(pdf_cmd)
            _run_command(pdf_cmd, dry_run=dry_run)

    logger.info("Collecting images...")
    images = collect_images(config, run_dir)
    if page_limit is not None:
        images = images[:page_limit]
    page_ids = resolve_page_ids(config, images)
    logger.info(f"Collected {len(images)} images.")

    run_detection = get_nested(config, "steps", "detection", default=False)
    probe_output_dir = None
    hybrid_output_dir = None

    if run_detection:
        logger.info("Starting detection step...")
        if skip_existing:
            if "detection" not in config:
                config["detection"] = {}
            config["detection"]["probe_skip_existing"] = True

        det_result = run_detection_step(
            config, images, page_ids, run_id_value, run_dir, dry_run=dry_run
        )
        commands.extend(det_result["commands"])
        probe_output_dir = det_result["probe_output_dir"]
        hybrid_output_dir = det_result["hybrid_output_dir"]

    excluded_indices = get_user_exclude_indices(config)
    excluded_page_ids = {page_ids[idx - 1] for idx in excluded_indices if 1 <= idx <= len(page_ids)}

    if run_detection and probe_output_dir and hybrid_output_dir:
        resolved = resolve_paths_from_detection(
            probe_output_dir, hybrid_output_dir, page_ids, images
        )
        page_runs = page_ids
    else:
        page_runs = _resolve_page_runs(config, page_ids)
        resolved = resolve_barlines_and_masks_config(
            config, page_ids, page_runs, excluded_page_ids=excluded_page_ids
        )

    page_statuses = resolve_page_filters(config, page_ids, images, resolved, excluded_indices)

    apply_barlines = get_nested(config, "steps", "apply_barline_overrides", default=False)
    user_overrides_path = get_nested(config, "inputs", "measure_overrides")
    barline_overrides_path = get_nested(config, "inputs", "barline_overrides")
    barline_override_payload = None
    if barline_overrides_path:
        barline_override_payload = load_json(Path(barline_overrides_path))

    barline_override_cfg = (
        get_nested(config, "inputs", "barline_overrides_config", default={}) or {}
    )
    barline_iou_threshold = float(barline_override_cfg.get("iou_threshold", 0.5))
    barline_min_width = int(barline_override_cfg.get("min_width", BARLINE_DEFAULT_MIN_WIDTH))
    barline_x_margin = int(barline_override_cfg.get("x_margin", BARLINE_X_MARGIN))
    barline_y_margin = int(barline_override_cfg.get("y_margin", BARLINE_Y_MARGIN))

    user_overrides_payload = None
    if user_overrides_path:
        user_overrides_payload = load_json(Path(user_overrides_path))

    force_single_system = bool(
        get_nested(config, "numbering", "force_single_system", default=False)
    )
    enable_rotation_tta = bool(get_nested(config, "mmr", "enable_rotation_tta", default=False))
    model_path = get_nested(config, "mmr", "model_path")
    model_path = Path(model_path) if model_path else None
    debug_root = get_nested(config, "mmr", "debug_root")
    debug_root = Path(debug_root) if debug_root else None

    step_numbering = get_nested(config, "steps", "numbering_base", default=False)
    step_mmr = get_nested(config, "steps", "mmr_overrides", default=False)
    step_apply = get_nested(config, "steps", "apply_measure_overrides", default=False)
    step_overlay = get_nested(config, "steps", "overlay", default=False)

    if not validate_only:
        if (step_mmr or step_apply or step_overlay) and not step_numbering:
            raise ValueError("numbering_base must be enabled before MMR or final numbering steps.")

    numbering_base_paths: List[Path] = []
    numbering_final_paths: List[Path] = []
    barline_override_stats: Dict[str, Dict[str, int]] = {}

    for index, (page_id, image_path, resolved_item) in tqdm(
        enumerate(zip(page_ids, images, resolved), start=1),
        total=len(page_ids),
        desc="Processing pages",
        unit="page",
    ):
        page_intermediate = intermediate_dir / page_id
        page_outputs = outputs_dir / page_id
        ensure_dir(page_intermediate)
        ensure_dir(page_outputs)

        if page_id in excluded_page_ids:
            empty_base = page_intermediate / "numbering_base.json"
            numbering_base_paths.append(empty_base)
            if not dry_run:
                write_json(empty_base, empty_numbering_payload(index, image_path))

            if (step_apply or step_overlay) and not validate_only:
                empty_final = page_outputs / "numbering_final.json"
                numbering_final_paths.append(empty_final)
                if not dry_run:
                    write_json(empty_final, empty_numbering_payload(index, image_path))
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
                raw_barlines = load_json(barlines_path)
                barlines_list = normalize_barlines(raw_barlines)
                corrected, stats = apply_barline_overrides(
                    barlines_list,
                    barline_override_payload.get("barline_overrides", []),
                    page_index=index - 1,
                    iou_threshold=barline_iou_threshold,
                    min_width=barline_min_width,
                    x_margin=barline_x_margin,
                    y_margin=barline_y_margin,
                )
                barline_override_stats[page_id] = stats
                if not dry_run:
                    write_json(corrected_path, corrected)
            else:
                if not dry_run and barlines_path.exists():
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
        cmd_base = build_add_measure_numbers_cmd(
            barlines=barlines_path,
            staff_mask=Path(resolved_item["staff_mask"]),
            image=image_path,
            output_json=numbering_base,
            page_number=index,
            start_number=1,
            force_single_system=force_single_system,
        )
        commands.append(cmd_base)
        if step_numbering and not validate_only:
            if skip_existing and numbering_base.exists():
                logger.info(f"Skipping numbering_base for {page_id}: file exists.")
            else:
                _run_command(cmd_base, dry_run=dry_run)

        mmr_overrides_payload = None
        if step_mmr and not validate_only:
            overrides_mmr = page_intermediate / "overrides_mmr.json"
            cmd_mmr = build_generate_overrides_cmd(
                numbering_json=numbering_base,
                image=image_path,
                output_overrides=overrides_mmr,
                model_path=model_path,
                enable_rotation_tta=enable_rotation_tta,
                debug_image=(debug_root / f"{page_id}_mmr_debug.png") if debug_root else None,
            )
            commands.append(cmd_mmr)
            if skip_existing and overrides_mmr.exists():
                logger.info(f"Skipping mmr_overrides for {page_id}: file exists.")
            else:
                _run_command(cmd_mmr, dry_run=dry_run)

            if not dry_run:
                # Still need to load the payload for subsequent steps even if skipped
                if overrides_mmr.exists():
                    mmr_overrides_payload = load_json(overrides_mmr)

        if (step_apply or step_overlay) and not validate_only:
            overrides_payload = merge_measure_overrides(
                mmr_overrides_payload, user_overrides_payload
            )
            combined_path = page_intermediate / "overrides_combined.json"
            if not dry_run:
                write_json(combined_path, overrides_payload)
            final_json = page_outputs / "numbering_final.json"
            numbering_final_paths.append(final_json)
            overlay_path = page_outputs / "numbering_overlay.png" if step_overlay else None
            cmd_final = build_add_measure_numbers_cmd(
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
            if (
                skip_existing
                and final_json.exists()
                and (not overlay_path or overlay_path.exists())
            ):
                logger.info(f"Skipping final_numbering for {page_id}: file exists.")
            else:
                _run_command(cmd_final, dry_run=dry_run)

    if len(numbering_base_paths) > 1 and not dry_run and not validate_only:
        combined_base = {
            "pages": [page for path in numbering_base_paths for page in load_json(path)["pages"]]
        }
        write_json(intermediate_dir / "numbering_base.json", combined_base)
    if len(numbering_final_paths) > 1 and not dry_run and not validate_only:
        combined_final = {
            "pages": [page for path in numbering_final_paths for page in load_json(path)["pages"]]
        }
        write_json(outputs_dir / "numbering_final.json", combined_final)

    if not dry_run:
        write_json(run_dir / "filters.json", {"pages": page_statuses})

    manifest = build_manifest(
        config,
        run_id=run_id_value,
        run_dir=run_dir,
        images=images,
        page_ids=page_ids,
        page_runs=page_runs,
        resolved=resolved,
        commands=commands,
        page_statuses=page_statuses,
        barline_override_stats=barline_override_stats,
    )
    write_manifest(run_dir / "manifest.json", manifest)
    logger.info(f"Wrote manifest to {run_dir / 'manifest.json'}")

    return run_dir


def main() -> None:
    import argparse
    import os

    # Optimization: Limit threads to avoid CPU contention and improve stability on WSL2
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Run the integrated detection and numbering pipeline."
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the YAML configuration file."
    )
    parser.add_argument("--run-id", type=str, help="Optional run identifier.")
    parser.add_argument("--output-root", type=Path, help="Optional output root directory.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Log commands without executing them."
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Stop after input resolution and filtering."
    )
    parser.add_argument(
        "--skip-existing", action="store_true", help="Skip steps if output files already exist."
    )
    parser.add_argument("--page-limit", type=int, help="Limit the number of pages to process.")

    args = parser.parse_args()

    from tqdm.contrib.logging import logging_redirect_tqdm

    with logging_redirect_tqdm():
        run_pipeline(
            args.config,
            run_id=args.run_id,
            output_root=args.output_root,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            skip_existing=args.skip_existing,
            page_limit=args.page_limit,
        )


if __name__ == "__main__":
    main()
