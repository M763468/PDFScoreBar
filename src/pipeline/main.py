"""End-to-end pipeline entrypoint (no CLI wrapper)."""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Optional

# Optimization: Limit threads to avoid CPU contention and improve stability on WSL2.
# This MUST be set before importing torch or onnxruntime.
DEFAULT_NUM_THREADS = "4"
os.environ.setdefault("OMP_NUM_THREADS", DEFAULT_NUM_THREADS)
os.environ.setdefault("MKL_NUM_THREADS", DEFAULT_NUM_THREADS)

from src.pipeline.core.config import get_nested, load_yaml
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.utils.io import ensure_dir

logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: Path,
    *,
    run_id: Optional[str] = None,
    output_root: Optional[Path] = None,
    dry_run: bool = False,
    validate_only: bool = False,
    skip_existing: bool = False,
    page_limit: Optional[int] = None,
    debug: bool = False,
    console_log_level: int = logging.INFO,
) -> Path:
    """Entry point for running the full pipeline."""
    from src.pipeline.detector_routes.production_dense import (
        normalize_runtime_detection_config,
    )
    from src.pipeline.utils.images import clear_image_cache

    clear_image_cache()

    config = load_yaml(config_path)
    normalize_runtime_detection_config(config)
    run_id_value = run_id or get_nested(config, "run", "run_id")
    if not run_id_value:
        run_id_value = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    output_root_value = output_root or get_nested(
        config, "run", "output_root", default="logs/full_pipeline_runs"
    )
    run_dir = Path(output_root_value) / run_id_value
    ensure_dir(run_dir)

    # Setup File Logging for this run
    log_file = run_dir / "pipeline.log"
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    # File log gets EVERYTHING (DEBUG and up)
    file_handler.setLevel(logging.DEBUG)

    root_logger = logging.getLogger()
    old_root_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Keep the file log diagnostic while allowing evaluation or automation
    # wrappers to make captured stdout/stderr quieter by default.
    old_handler_levels = []
    for handler in root_logger.handlers:
        if handler == file_handler:
            continue
        old_handler_levels.append((handler, handler.level))
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setLevel(console_log_level)

    try:
        logger.info(f"Starting pipeline run: {run_id_value}")
        logger.info(f"Run directory: {run_dir}")
        logger.info(f"Log file: {log_file}")

        orchestrator = PipelineOrchestrator(
            config=config,
            run_id=run_id_value,
            run_dir=run_dir,
            dry_run=dry_run,
            validate_only=validate_only,
            skip_existing=skip_existing,
            debug=debug,
        )

        return orchestrator.run(page_limit=page_limit)

    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()
        root_logger.setLevel(old_root_level)
        for h, level in old_handler_levels:
            h.setLevel(level)


def main() -> None:
    """CLI entry point for the pipeline."""
    import argparse

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
    parser.add_argument("--debug", action="store_true", help="Output intermediate debug files.")

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
            debug=args.debug,
        )


if __name__ == "__main__":
    main()
