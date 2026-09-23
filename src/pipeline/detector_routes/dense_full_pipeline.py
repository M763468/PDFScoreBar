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

from src.common.barline_evaluation import barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.steps.probe_scan import run_probe_scan_batch

logger = logging.getLogger(__name__)

DENSE_ROUTE_EXPECTED_PAGES = 68
DEFAULT_LOG_HEAD_LINES = 200
DEFAULT_LOG_TAIL_LINES = 200
LATE_RAW_X4_IOU_THRESHOLD = 0.5

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
    cnn_band_sources: dict[Path, Path]
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
        log_file.write(
            "# Full verbose logs are disabled by default for Issue #159 log-volume control.\n"
        )
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


def _run_command(
    cmd: list[str], *, log_path: Path, verbose_logs: bool = False
) -> CommandLogSummary:
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


def _normalize_box(box: list[int] | tuple[int, ...]) -> tuple[int, int, int, int]:
    if len(box) != 4:
        raise ValueError(f"Expected 4-value bbox, got {box!r}")
    return tuple(int(v) for v in box)


def build_late_raw_x4_union(
    *,
    raw_boxes: list[list[int]] | list[tuple[int, int, int, int]],
    x4_boxes: list[list[int]] | list[tuple[int, int, int, int]],
    iou_threshold: float = LATE_RAW_X4_IOU_THRESHOLD,
) -> tuple[list[list[int]], list[list[int]]]:
    """Add x4 boxes not represented by the already-generated raw candidate set."""

    raw_norm = [_normalize_box(box) for box in raw_boxes]
    promoted = [
        _normalize_box(box)
        for box in x4_boxes
        if not any(barline_iou(_normalize_box(box), raw) > iou_threshold for raw in raw_norm)
    ]

    seen: set[tuple[int, int, int, int]] = set()
    union: list[list[int]] = []
    unique_promoted: list[list[int]] = []
    promoted_set = set(promoted)
    for box in [*raw_norm, *promoted]:
        if box in seen:
            continue
        seen.add(box)
        union.append(list(box))
        if box in promoted_set and box not in raw_norm:
            unique_promoted.append(list(box))
    return union, unique_promoted


def inject_current_x4_gaps(
    *,
    inventory: Path,
    exclude: Path,
    raw_root: Path,
    summary_out: Path,
) -> dict[str, Any]:
    """Apply the Issue #372 late-raw compatibility boundary in-place."""

    payload = json.loads(inventory.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Dense route inventory records must be a list")

    exclude_payload = json.loads(exclude.read_text(encoding="utf-8")) if exclude.exists() else {}
    excluded = {
        (str(row["score"]), str(row["page"]))
        for row in exclude_payload.get("excluded_pages", [])
        if isinstance(row, dict) and "score" in row and "page" in row
    }

    rows: list[dict[str, Any]] = []
    for record in records:
        score = str(record["score"])
        page = str(record["page"])
        if (score, page) in excluded:
            continue

        x4_raw = record.get("current_x4_detection")
        if not x4_raw:
            raise ValueError(f"{score}/{page}: inventory lacks current_x4_detection")
        x4_path = Path(str(x4_raw))
        if not x4_path.is_file():
            raise FileNotFoundError(x4_path)

        raw_path = raw_root / score / page / "pipeline2_no_peak_candidates.json"
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)

        raw_boxes = [list(box) for box in load_json_boxes(raw_path)]
        x4_boxes = [list(box) for box in load_json_boxes(x4_path)]
        union, promoted = build_late_raw_x4_union(
            raw_boxes=raw_boxes,
            x4_boxes=x4_boxes,
        )
        raw_path.write_text(json.dumps(union, indent=2) + "\n", encoding="utf-8")
        rows.append(
            {
                "score": score,
                "page": page,
                "raw_count_before": len(raw_boxes),
                "x4_count": len(x4_boxes),
                "promoted_x4_count": len(promoted),
                "raw_count_after": len(union),
                "current_x4_detection": str(x4_path),
                "raw_candidates": str(raw_path),
            }
        )

    summary = {
        "schema_version": "pipeline.detector_routes.dense_full_pipeline.late_raw_x4.v1",
        "injection_boundary": "after initial raw generation, before candidate filter",
        "iou_threshold": LATE_RAW_X4_IOU_THRESHOLD,
        "processed": len(rows),
        "pages_with_promotions": sum(row["promoted_x4_count"] > 0 for row in rows),
        "total_promoted_x4_boxes": sum(row["promoted_x4_count"] for row in rows),
        "per_page": rows,
    }
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def load_frozen_hybrid_band_sources(
    *,
    inventory: Path,
    exclude: Path,
) -> dict[Path, Path]:
    """Map each route image to its pre-probe hybrid geometry authority."""

    payload = json.loads(inventory.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Dense route inventory records must be a list")

    exclude_payload = json.loads(exclude.read_text(encoding="utf-8")) if exclude.exists() else {}
    excluded = {
        (str(row["score"]), str(row["page"]))
        for row in exclude_payload.get("excluded_pages", [])
        if isinstance(row, dict) and "score" in row and "page" in row
    }

    result: dict[Path, Path] = {}
    for record in records:
        score = str(record["score"])
        page = str(record["page"])
        if (score, page) in excluded:
            continue
        image = Path(str(record["image"])).resolve()
        hybrid = Path(str(record["hybrid_predictions"])).resolve()
        if not image.is_file():
            raise FileNotFoundError(image)
        if not hybrid.is_file():
            raise FileNotFoundError(hybrid)
        result[image] = hybrid
    return result


def regenerate_dense_candidates(
    *,
    inventory: Path,
    exclude: Path,
    route_root: Path,
    expected_pages: int = DENSE_ROUTE_EXPECTED_PAGES,
    verbose_logs: bool = False,
    phase_summaries: list[dict[str, Any]] | None = None,
) -> Path:
    """Regenerate the dense candidate/filter root inside this route run."""
    dense_root = route_root / "dense_candidate_reconstruction"
    raw_root = dense_root / "probe_candidates_from_inventory"
    filtered_root = dense_root / "probe_candidates_filtered"
    suggestions_root = dense_root / "filter_suggestions"
    generation_summary = dense_root / "probe_generation_summary.json"
    filter_summary = dense_root / "filter_apply_summary.json"
    late_raw_summary = dense_root / "late_raw_x4_injection_summary.json"
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
        _run_command(
            gen_cmd,
            log_path=log_dir / "01_generate_probe_candidates.log",
            verbose_logs=verbose_logs,
        )
    )

    late_raw = inject_current_x4_gaps(
        inventory=inventory,
        exclude=exclude,
        raw_root=raw_root,
        summary_out=late_raw_summary,
    )
    if late_raw["processed"] != expected_pages:
        raise RuntimeError(
            "Late-raw x4 injection did not cover the dense route: "
            f"processed={late_raw['processed']} expected={expected_pages}"
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
        _run_command(
            filter_cmd,
            log_path=log_dir / "02_apply_candidate_filter.log",
            verbose_logs=verbose_logs,
        )
    )

    summary = json.loads(filter_summary.read_text())
    if summary.get("processed") != expected_pages or summary.get("errors") != 0:
        raise RuntimeError(
            "Dense candidate reconstruction did not complete cleanly: "
            f"processed={summary.get('processed')} expected={expected_pages} "
            f"errors={summary.get('errors')}"
        )
    if phase_summaries is not None:
        phase_summaries.append(
            _phase_summary(
                "dense_candidate_reconstruction",
                phase_started,
                output_root=str(dense_root),
                raw_root=str(raw_root),
                filtered_root=str(filtered_root),
                suggestions_root=str(suggestions_root),
                generation_summary=str(generation_summary),
                filter_summary=str(filter_summary),
                late_raw_x4_summary=str(late_raw_summary),
                late_raw_x4_promoted=int(late_raw["total_promoted_x4_boxes"]),
                command_logs=[command.to_json() for command in command_summaries],
            )
        )
    return filtered_root


def regenerate_probe_rescue_candidates(
    *,
    image_paths: list[Path],
    filtered_root: Path,
    route_root: Path,
    phase_summaries: list[dict[str, Any]] | None = None,
) -> Path:
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
        raise RuntimeError(
            f"Probe-rescue candidate reconstruction processed {processed}/{expected_pages} pages"
        )
    if phase_summaries is not None:
        phase_summaries.append(
            _phase_summary(
                "probe_rescue_candidate_reconstruction",
                phase_started,
                output_root=str(probe_rescue_root),
                processed_pages=processed,
                expected_pages=expected_pages,
            )
        )
    return probe_rescue_root


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

    cnn_band_sources = load_frozen_hybrid_band_sources(
        inventory=inventory,
        exclude=exclude,
    )
    if len(cnn_band_sources) != len(image_paths):
        raise RuntimeError(
            "Frozen hybrid band-source count does not match route images: "
            f"bands={len(cnn_band_sources)} images={len(image_paths)}"
        )

    filtered_root = regenerate_dense_candidates(
        inventory=inventory,
        exclude=exclude,
        route_root=route_root,
        expected_pages=len(image_paths),
        verbose_logs=verbose_logs,
        phase_summaries=phases,
    )
    probe_rescue_root = regenerate_probe_rescue_candidates(
        image_paths=image_paths,
        filtered_root=filtered_root,
        route_root=route_root,
        phase_summaries=phases,
    )

    execution_summary = {
        "schema_version": "pipeline.detector_routes.dense_full_pipeline.execution_summary.v1",
        "log_mode": "verbose" if verbose_logs else "compact",
        "expected_pages": expected_pages,
        "image_count": len(image_paths),
        "total_duration_sec": time.perf_counter() - started_at,
        "artifacts": {
            "filtered_root": str(filtered_root),
            "probe_rescue_root": str(probe_rescue_root),
            "cnn_band_source": "pre_probe_hybrid_inventory",
            "cnn_band_source_count": len(cnn_band_sources),
        },
        "phases": phases,
    }
    summary_path = _write_execution_summary(route_root, execution_summary)
    execution_summary["summary_path"] = str(summary_path)

    return DenseRouteArtifacts(
        image_paths=image_paths,
        filtered_root=filtered_root,
        probe_rescue_root=probe_rescue_root,
        cnn_band_sources=cnn_band_sources,
        execution_summary=execution_summary,
    )
