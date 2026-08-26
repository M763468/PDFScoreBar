"""Run persistent multi-page cuDNN benchmark screening for Issue #284."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VARIANTS = (
    ("benchmark_off_a", False),
    ("benchmark_on", True),
    ("benchmark_off_b", False),
)


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 persistent cuDNN sweep requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _bundle(output: Path, paths: list[Path]) -> Path:
    bundle = output / "issue284_persistent_cudnn_sweep_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=600.0)
    args = parser.parse_args()

    _require_runtime()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    reference_dir = output / "benchmark_off_a_outputs"
    records: list[dict[str, Any]] = []
    share_paths: list[Path] = []

    for name, benchmark in VARIANTS:
        variant_output = output / f"{name}_outputs"
        result_path = output / f"{name}.json"
        log_path = output / f"{name}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_persistent_cudnn_variant.py"),
            "--output-dir",
            str(variant_output),
            "--result",
            str(result_path),
        ]
        if benchmark:
            command.append("--benchmark")
        if name != "benchmark_off_a":
            command.extend(["--reference-dir", str(reference_dir)])

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

        payload = _load(result_path)
        record: dict[str, Any] = {
            "variant": name,
            "benchmark": benchmark,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": time.perf_counter() - started,
            "status": payload.get("status")
            if payload
            else ("timeout" if timed_out else "missing_result"),
        }
        if payload:
            record.update(
                {
                    "model_init_sec": payload.get("model_init_sec"),
                    "enhance_total_wall_sec": payload.get("enhance_total_wall_sec"),
                    "pages": payload.get("pages"),
                    "all_array_equal": payload.get("all_array_equal"),
                    "peak_cuda_allocated_bytes": payload.get("peak_cuda_allocated_bytes"),
                    "peak_cuda_reserved_bytes": payload.get("peak_cuda_reserved_bytes"),
                    "device_total_bytes": payload.get("device_total_bytes"),
                    "backend": payload.get("backend"),
                }
            )
        records.append(record)
        share_paths.extend([result_path, log_path])
        if name == "benchmark_off_a" and record["status"] != "completed":
            break

    off_times = [
        float(item["enhance_total_wall_sec"])
        for item in records
        if item.get("status") == "completed"
        and item.get("benchmark") is False
        and item.get("enhance_total_wall_sec") is not None
    ]
    on_record = next(
        (
            item
            for item in records
            if item.get("status") == "completed" and item.get("benchmark") is True
        ),
        None,
    )
    off_mean = sum(off_times) / len(off_times) if off_times else None
    on_time = (
        float(on_record["enhance_total_wall_sec"])
        if on_record and on_record.get("enhance_total_wall_sec") is not None
        else None
    )
    speedup = off_mean / on_time if off_mean and on_time else None

    summary = {
        "schema_version": "issue284.persistent_cudnn_sweep.v1",
        "fixed_runtime": {
            "channels_last": True,
            "fp16": True,
            "inference_mode": True,
            "tile": 400,
            "tile_pad": 10,
            "model_lifetime": "one process across three real pages",
        },
        "variants": records,
        "benchmark_off_mean_enhance_sec": off_mean,
        "benchmark_on_enhance_sec": on_time,
        "benchmark_on_speedup_vs_off_mean": speedup,
        "benchmark_on_reduction_fraction": 1.0 - 1.0 / speedup if speedup else None,
        "notes": [
            "benchmark_off is measured before and after benchmark_on to expose run-order noise.",
            "Only cuDNN benchmark mode changes; the current channels-last CPU-stitch runtime is otherwise unchanged.",
            "A material winner must retain acceptable output behavior before production adoption.",
        ],
    }
    summary_path = output / "persistent_cudnn_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    share_paths.append(summary_path)
    bundle = _bundle(output, share_paths)

    print(json.dumps(summary, indent=2))
    print(f"share_bundle={bundle}")
    return 0 if off_times and on_record else 1


if __name__ == "__main__":
    raise SystemExit(main())
