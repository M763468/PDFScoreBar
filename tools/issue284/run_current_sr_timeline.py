"""Run repeated current-SR utilization/timeline profiles and build one share bundle."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCORE = "Shostakovich-Sym5-Va"
PAGE = "page_013"


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 SR timeline runner requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _reference_image(candidate_summary: Path) -> Path:
    summary = _load_json(candidate_summary)
    scores = summary.get("scores")
    if not isinstance(scores, list):
        raise ValueError("Candidate summary lacks scores")
    score = next((item for item in scores if item.get("score") == SCORE), None)
    if not isinstance(score, dict):
        raise ValueError(f"Candidate summary lacks score {SCORE}")
    artifacts = score.get("page_artifacts")
    if not isinstance(artifacts, dict) or PAGE not in artifacts:
        raise ValueError(f"Candidate summary lacks {SCORE}/{PAGE}")
    page = artifacts[PAGE]
    if not isinstance(page, dict):
        raise ValueError(f"Invalid page artifacts for {PAGE}")
    support_path = Path(str(page.get("current_support", ""))).resolve()
    support = _load_json(support_path)
    sr_image = Path(str(support.get("sr_image", ""))).resolve()
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)
    return sr_image


def _read_samples(path: Path) -> list[dict[str, float]]:
    samples: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                samples.append(
                    {key: float(value) for key, value in row.items() if value is not None}
                )
            except ValueError:
                continue
    return samples


def _inside(value: float, intervals: list[tuple[float, float]]) -> bool:
    return any(start <= value <= end for start, end in intervals)


def _util_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "p50": statistics.median(values),
        "max": max(values),
    }


def _phase_utilization(payload: dict[str, Any], sample_path: Path) -> dict[str, Any]:
    tiles = payload.get("tile_timeline") or []
    forward_intervals = [
        (float(item["forward_start_sec"]), float(item["forward_end_sec"])) for item in tiles
    ]
    copy_intervals = [
        (float(item["copy_start_sec"]), float(item["copy_end_sec"])) for item in tiles
    ]
    samples = _read_samples(sample_path)
    overall = [sample["utilization.gpu"] for sample in samples if "utilization.gpu" in sample]
    forward = [
        sample["utilization.gpu"]
        for sample in samples
        if "utilization.gpu" in sample and _inside(sample["relative_sec"], forward_intervals)
    ]
    copy = [
        sample["utilization.gpu"]
        for sample in samples
        if "utilization.gpu" in sample and _inside(sample["relative_sec"], copy_intervals)
    ]
    outside = [
        sample["utilization.gpu"]
        for sample in samples
        if "utilization.gpu" in sample
        and not _inside(sample["relative_sec"], forward_intervals)
        and not _inside(sample["relative_sec"], copy_intervals)
    ]
    denominator = len(overall)
    idle_fractions = {
        f"below_{threshold}_fraction": (
            sum(value < threshold for value in overall) / denominator if denominator else None
        )
        for threshold in (25, 50, 75, 90)
    }
    return {
        "overall": _util_stats(overall),
        "forward": _util_stats(forward),
        "copy": _util_stats(copy),
        "outside_forward_copy": _util_stats(outside),
        "idle_fractions": idle_fractions,
    }


def _bundle(output: Path, paths: list[Path]) -> Path:
    bundle = output / "issue284_current_sr_timeline_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument("--sample-interval-ms", type=int, default=100)
    args = parser.parse_args()

    _require_runtime()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    candidate_summary = args.candidate_summary.resolve()
    reference = _reference_image(candidate_summary)

    records: list[dict[str, Any]] = []
    share_paths: list[Path] = []
    for repetition in range(1, args.repetitions + 1):
        result_path = output / f"rep{repetition}.json"
        samples_path = output / f"rep{repetition}_gpu_samples.csv"
        log_path = output / f"rep{repetition}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_current_sr_timeline.py"),
            "--reference-image",
            str(reference),
            "--result",
            str(result_path),
            "--gpu-samples",
            str(samples_path),
            "--sample-interval-ms",
            str(args.sample_interval_ms),
        ]
        started = time.perf_counter()
        timed_out = False
        returncode: int | None = None
        with log_path.open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=args.timeout_sec,
                )
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        process_wall = time.perf_counter() - started
        payload = _load_json(result_path) if result_path.is_file() else None
        record: dict[str, Any] = {
            "repetition": repetition,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": process_wall,
            "status": payload.get("status") if payload else ("timeout" if timed_out else "missing"),
            "result": str(result_path),
            "gpu_samples": str(samples_path),
            "log": str(log_path),
        }
        if payload:
            record.update(
                {
                    "total_wall_sec": payload.get("total_wall_sec"),
                    "tile_count": payload.get("tile_count"),
                    "timing_summary": payload.get("timing_summary"),
                    "memory": payload.get("memory"),
                    "comparison": payload.get("comparison"),
                    "gpu_summary": (payload.get("gpu_samples") or {}).get("summary"),
                    "gpu_sampler_error": (payload.get("gpu_samples") or {}).get("error"),
                    "phase_utilization": (
                        _phase_utilization(payload, samples_path)
                        if samples_path.is_file()
                        else None
                    ),
                }
            )
        records.append(record)
        share_paths.extend([result_path, samples_path, log_path])

    completed = [item for item in records if item.get("status") == "completed"]
    walls = [float(item["total_wall_sec"]) for item in completed if item.get("total_wall_sec")]
    forward_totals = [
        float((item.get("timing_summary") or {}).get("forward_total_sec"))
        for item in completed
        if (item.get("timing_summary") or {}).get("forward_total_sec") is not None
    ]
    copy_totals = [
        float((item.get("timing_summary") or {}).get("copy_total_sec"))
        for item in completed
        if (item.get("timing_summary") or {}).get("copy_total_sec") is not None
    ]
    summary = {
        "schema_version": "issue284.current_sr_timeline_sweep.v1",
        "candidate_summary": str(candidate_summary),
        "reference_image": str(reference),
        "repetitions": args.repetitions,
        "sample_interval_ms": args.sample_interval_ms,
        "runs": records,
        "aggregate": {
            "completed_runs": len(completed),
            "total_wall_sec_median": statistics.median(walls) if walls else None,
            "forward_total_sec_median": statistics.median(forward_totals)
            if forward_totals
            else None,
            "copy_total_sec_median": statistics.median(copy_totals) if copy_totals else None,
        },
        "interpretation_gate": {
            "parallelism_not_ruled_out": True,
            "next_step": (
                "Use phase utilization and idle fractions to decide whether to prioritize "
                "torch.compile, CUDA-stream N=1 concurrency, or D2H/stitch overlap."
            ),
        },
    }
    summary_path = output / "current_sr_timeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    share_paths.append(summary_path)
    bundle = _bundle(output, share_paths)
    print(json.dumps(summary, indent=2))
    print(f"share_bundle={bundle}")
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
