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
from src.pipeline.engine_contract import JobStatus, ProgressCallback, canonical_json
from src.pipeline.engine_telemetry import TelemetryRecorder
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
    on_progress: ProgressCallback | None = None,
    telemetry_summary_path: Path | None = None,
    sample_resources: bool = False,
    resource_sample_interval_seconds: float = 1.0,
) -> Path:
    """Entry point for running the full pipeline."""
    from src.pipeline.utils.images import clear_image_cache

    clear_image_cache()

    config = load_yaml(config_path)
    run_id_value = run_id or get_nested(config, "run", "run_id")
    if not run_id_value:
        run_id_value = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    output_root_value = output_root or get_nested(
        config, "run", "output_root", default="logs/full_pipeline_runs"
    )
    run_dir = Path(output_root_value) / run_id_value
    ensure_dir(run_dir)

    effective_telemetry_summary_path = telemetry_summary_path
    if sample_resources and effective_telemetry_summary_path is None:
        effective_telemetry_summary_path = run_dir / "telemetry.json"

    telemetry = None

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
        if (
            on_progress is not None
            or effective_telemetry_summary_path is not None
            or sample_resources
        ):
            telemetry = TelemetryRecorder(
                run_id_value,
                on_progress=on_progress,
                sample_resources=sample_resources,
                resource_sample_interval_seconds=resource_sample_interval_seconds,
            )
            telemetry.start_job()

        logger.info(f"Starting pipeline run: {run_id_value}")
        logger.info(f"Run directory: {run_dir}")
        logger.info(f"Log file: {log_file}")

        try:
            orchestrator = PipelineOrchestrator(
                config=config,
                run_id=run_id_value,
                run_dir=run_dir,
                dry_run=dry_run,
                validate_only=validate_only,
                skip_existing=skip_existing,
                debug=debug,
                telemetry=telemetry,
            )
            result = orchestrator.run(page_limit=page_limit)
        except Exception:
            if telemetry is not None:
                telemetry.terminal(JobStatus.FAILED)
            raise
        else:
            if telemetry is not None:
                telemetry.terminal(JobStatus.SUCCEEDED)
            return result

    finally:
        if telemetry is not None:
            telemetry.close()
            if effective_telemetry_summary_path is not None:
                try:
                    effective_telemetry_summary_path.parent.mkdir(parents=True, exist_ok=True)
                    effective_telemetry_summary_path.write_text(
                        canonical_json(telemetry.summary()) + "\n",
                        encoding="utf-8",
                    )
                except Exception:
                    logger.exception("Failed to write structured telemetry summary.")
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
    parser.add_argument(
        "--progress-jsonl",
        type=Path,
        help="Optional JSONL file receiving structured progress events.",
    )
    parser.add_argument(
        "--telemetry-summary",
        type=Path,
        help="Optional JSON file receiving the compact stage/resource summary.",
    )
    parser.add_argument(
        "--sample-resources",
        action="store_true",
        help="Opt in to lightweight process-tree/GPU resource sampling.",
    )
    parser.add_argument(
        "--resource-sample-interval-seconds",
        type=float,
        default=1.0,
        help="Resource sampling interval when --sample-resources is enabled.",
    )

    args = parser.parse_args()

    from tqdm.contrib.logging import logging_redirect_tqdm

    progress_stream = None
    on_progress = None
    if args.progress_jsonl is not None:
        args.progress_jsonl.parent.mkdir(parents=True, exist_ok=True)
        progress_stream = args.progress_jsonl.open("w", encoding="utf-8")

        def write_progress(event):
            assert progress_stream is not None
            progress_stream.write(event.to_json() + "\n")
            progress_stream.flush()

        on_progress = write_progress

    try:
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
                on_progress=on_progress,
                telemetry_summary_path=args.telemetry_summary,
                sample_resources=args.sample_resources,
                resource_sample_interval_seconds=args.resource_sample_interval_seconds,
            )
    finally:
        if progress_stream is not None:
            progress_stream.close()


if __name__ == "__main__":
    main()
