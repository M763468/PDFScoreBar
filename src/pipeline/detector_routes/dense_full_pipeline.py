"""Dense full-pipeline detector route support.

This module reconstructs detector-route inputs from current-run inventory data,
then exposes them through the production ``DetectorOrchestrator`` config/API.
Historical checkpoint aliases are kept in the dedicated compatibility shim,
not in this production-oriented route module.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pipeline.steps.probe_scan import run_probe_scan_batch

logger = logging.getLogger(__name__)

DENSE_ROUTE_EXPECTED_PAGES = 68
DEFAULT_LOG_HEAD_LINES = 200
DEFAULT_LOG_TAIL_LINES = 200

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


@dataclass(frozen=True)
class DenseRouteArtifacts:
    """Freshly reconstructed dense route inputs."""

    image_paths: list[Path]
    filtered_root: Path
    probe_rescue_root: Path
    execution_summary: dict[str, Any] | None = None


@dataclass(frozen=True)
class CommandLogSummary:
    command: list[str]
    log_path: Path
    log_mode: str
    returncode: int
    duration_sec: float
    output_lines: int
    output_bytes: int
    omitted_middle_lines: int
    log_size_bytes: int

    def to_json(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "log_path": str(self.log_path),
            "log_mode": self.log_mode,
            "returncode": self.returncode,
            "duration_sec": self.duration_sec,
            "output_lines": self.output_lines,
            "output_bytes": self.output_bytes,
            "omitted_middle_lines": self.omitted_middle_lines,
            "log_size_bytes": self.log_size_bytes,
        }


def _add_params(cmd: list[str], params: dict[str, str]) -> None:
    for key, value in params.items():
        cmd.extend([f"--{key.replace('_', '-')}", value])


def _compact_log_path(log_path: Path) -> Path:
    if log_path.suffix:
        return log_path.with_name(f"{log_path.stem}.compact{log_path.suffix}")
    return log_path.with_name(f"{log_path.name}.compact")


def _write_compact_log(
    log_path: Path,
    *,
    cmd: list[str],
    process: subprocess.Popen[str],
    started_at: float,
    head_lines_limit: int = DEFAULT_LOG_HEAD_LINES,
    tail_lines_limit: int = DEFAULT_LOG_TAIL_LINES,
) -> CommandLogSummary:
    head: list[str] = []
    tail: deque[str] = deque(maxlen=tail_lines_limit)
    output_lines = 0
    output_bytes = 0

    assert process.stdout is not None
    for line in process.stdout:
        output_lines += 1
        output_bytes += len(line.encode("utf-8", errors="replace"))
        if len(head) < head_lines_limit:
            head.append(line)
        else:
            tail.append(line)

    returncode = process.wait()
    duration_sec = time.perf_counter() - started_at
    omitted_middle_lines = max(output_lines - len(head) - len(tail), 0)

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write("# Compact command log\n")
        log_file.write("# Full verbose logs are disabled by default for Issue #159 log-volume control.\n")
        log_file.write("# Command: " + " ".join(str(part) for part in cmd) + "\n")
        log_file.write(f"# Return code: {returncode}\n")
        log_file.write(f"# Duration seconds: {duration_sec:.3f}\n")
        log_file.write(f"# Captured output lines: {output_lines}\n")
        log_file.write(f"# Captured output bytes: {output_bytes}\n")
        log_file.write(f"# Head lines retained: {len(head)}\n")
        log_file.write(f"# Tail lines retained: {len(tail)}\n")
        log_file.write(f"# Omitted middle lines: {omitted_middle_lines}\n\n")
        log_file.writelines(head)
        if omitted_middle_lines:
            log_file.write(f"\n# ... omitted {omitted_middle_lines} middle log lines ...\n\n")
        if omitted_middle_lines or output_lines > len(head):
            log_file.writelines(tail)

    return CommandLogSummary(
        command=cmd,
        log_path=log_path,
        log_mode="compact",
        returncode=returncode,
        duration_sec=duration_sec,
        output_lines=output_lines,
        output_bytes=output_bytes,
        omitted_middle_lines=omitted_middle_lines,
        log_size_bytes=log_path.stat().st_size,
    )


def _run_command(cmd: list[str], *, log_path: Path, verbose_logs: bool = False) -> CommandLogSummary:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    effective_log_path = log_path if verbose_logs else _compact_log_path(log_path)
    logger.info("+ %s > %s", " ".join(cmd), effective_log_path)
    started_at = time.perf_counter()

    if verbose_logs:
        with effective_log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        duration_sec = time.perf_counter() - started_at
        summary = CommandLogSummary(
            command=cmd,
            log_path=effective_log_path,
            log_mode="verbose",
            returncode=process.returncode,
            duration_sec=duration_sec,
            output_lines=-1,
            output_bytes=-1,
            omitted_middle_lines=0,
            log_size_bytes=effective_log_path.stat().st_size,
        )
    else:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        summary = _write_compact_log(
            effective_log_path,
            cmd=cmd,
            process=process,
            started_at=started_at,
        )

    if summary.returncode != 0:
        raise subprocess.CalledProcessError(summary.returncode, cmd)
    return summary


def _phase_summary(name: str, started_at: float, **extra: Any) -> dict[str, Any]:
    return {"name": name, "duration_sec": time.perf_counter() - started_at, **extra}


def _write_execution_summary(route_root: Path, summary: dict[str, Any]) -> Path:
    path = route_root / "dense_route_execution_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_route_image_paths(
    *,
    inventory: Path,
    exclude: Path,
    expected_pages: int = DENSE_ROUTE_EXPECTED_PAGES,
) -> list[Path]:
    """Load the detector-route image list from a benchmark inventory."""
    inv = json.loads(inventory.read_text())
    exclude_list = []
    if exclude.exists():
        exclude_list = json.loads(exclude.read_text()).get("excluded_pages", [])

    image_paths: list[Path] = []
    for rec in inv.get("records", []):
        score = rec["score"]
        page = rec["page"]
        if {"score": score, "page": page} in exclude_list:
            continue
        image_paths.append(Path(rec["image"]))

    if len(image_paths) != expected_pages:
        raise RuntimeError(f"Expected {expected_pages} dense-route images, got {len(image_paths)}")
    return image_paths


def regenerate_dense_candidates(
    *,
    inventory: Path,
    exclude: Path,
    route_root: Path,
    expected_pages: int = DENSE_ROUTE_EXPECTED_PAGES,
    verbose_logs: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Regenerate the dense candidate/filter root inside this route run."""
    dense_root = route_root / "dense_candidate_reconstruction"
    raw_root = dense_root / "probe_candidates_from_inventory"
    filtered_root = dense_root / "probe_candidates_filtered"
    suggestions_root = dense_root / "filter_suggestions"
    generation_summary = dense_root / "probe_generation_summary.json"
    filter_summary = dense_root / "filter_apply_summary.json"
    log_dir = dense_root / "logs"

    if dense_root.exists():
        shutil.rmtree(dense_root)
    dense_root.mkdir(parents=True, exist_ok=True)

    phase_started = time.perf_counter()
    command_summaries: list[CommandLogSummary] = []

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
    command_summaries.append(
        _run_command(gen_cmd, log_path=log_dir / "01_generate_probe_candidates.log", verbose_logs=verbose_logs)
    )

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
    command_summaries.append(
        _run_command(filter_cmd, log_path=log_dir / "02_apply_candidate_filter.log", verbose_logs=verbose_logs)
    )

    summary = json.loads(filter_summary.read_text())
    if summary.get("processed") != expected_pages or summary.get("errors") != 0:
        raise RuntimeError(
            "Dense candidate reconstruction did not complete cleanly: "
            f"processed={summary.get('processed')} expected={expected_pages} "
            f"errors={summary.get('errors')}"
        )
    phase = _phase_summary(
        "dense_candidate_reconstruction",
        phase_started,
        output_root=str(dense_root),
        raw_root=str(raw_root),
        filtered_root=str(filtered_root),
        suggestions_root=str(suggestions_root),
        generation_summary=str(generation_summary),
        filter_summary=str(filter_summary),
        command_logs=[command.to_json() for command in command_summaries],
    )
    return filtered_root, phase


def regenerate_probe_rescue_candidates(
    *,
    image_paths: list[Path],
    filtered_root: Path,
    route_root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Regenerate probe-rescue candidates for the dense detector route."""
    phase_started = time.perf_counter()
    probe_rescue_root = route_root / "dense_candidate_reconstruction" / "probe_rescue_candidates"
    shutil.rmtree(probe_rescue_root, ignore_errors=True)
    probe_rescue_root.mkdir(parents=True, exist_ok=True)

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
        output_root=probe_rescue_root,
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
    expected_pages = len(image_paths)
    if processed != expected_pages:
        raise RuntimeError(f"Probe-rescue candidate reconstruction processed {processed}/{expected_pages} pages")
    phase = _phase_summary(
        "probe_rescue_candidate_reconstruction",
        phase_started,
        output_root=str(probe_rescue_root),
        processed_pages=processed,
        expected_pages=expected_pages,
    )
    return probe_rescue_root, phase


def reconstruct_dense_full_pipeline_route(
    *,
    inventory: Path,
    exclude: Path,
    route_root: Path,
    expected_pages: int = DENSE_ROUTE_EXPECTED_PAGES,
    verbose_logs: bool = False,
) -> DenseRouteArtifacts:
    """Rebuild all dense full-pipeline detector inputs from current-run sources."""
    started_at = time.perf_counter()
    phases: list[dict[str, Any]] = []

    phase_started = time.perf_counter()
    image_paths = load_route_image_paths(
        inventory=inventory,
        exclude=exclude,
        expected_pages=expected_pages,
    )
    phases.append(
        _phase_summary(
            "load_route_image_paths",
            phase_started,
            inventory=str(inventory),
            exclude=str(exclude),
            image_count=len(image_paths),
        )
    )

    filtered_root, dense_phase = regenerate_dense_candidates(
        inventory=inventory,
        exclude=exclude,
        route_root=route_root,
        expected_pages=len(image_paths),
        verbose_logs=verbose_logs,
    )
    phases.append(dense_phase)

    probe_rescue_root, probe_phase = regenerate_probe_rescue_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        route_root=route_root,
    )
    phases.append(probe_phase)

    execution_summary = {
        "schema_version": "pipeline.detector_routes.dense_full_pipeline.execution_summary.v1",
        "log_mode": "verbose" if verbose_logs else "compact",
        "expected_pages": expected_pages,
        "image_count": len(image_paths),
        "total_duration_sec": time.perf_counter() - started_at,
        "artifacts": {
            "filtered_root": str(filtered_root),
            "probe_rescue_root": str(probe_rescue_root),
        },
        "phases": phases,
    }
    summary_path = _write_execution_summary(route_root, execution_summary)
    execution_summary["summary_path"] = str(summary_path)

    return DenseRouteArtifacts(
        image_paths=image_paths,
        filtered_root=filtered_root,
        probe_rescue_root=probe_rescue_root,
        execution_summary=execution_summary,
    )
