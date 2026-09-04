#!/usr/bin/env python3
"""Run the Issue #294 pinned-vs-maintained HOMR same-original A/B gate.

Both variants run as fresh top-level processes for every page. Variant A uses
the production ``stage_e_verified`` profile unchanged. Variant B uses the
experiment-only maintained-HOMR original-image worker in this directory.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from src.pipeline.detection.homr_profile import (
    build_profile_command,
    build_profile_environment,
    load_homr_profile,
    validate_profile_runtime,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
PROFILE_NAME = "stage_e_verified"


class ResourceSampler:
    """Best-effort process-tree RSS and device-level GPU memory sampler."""

    def __init__(self, pid: int, output: Path, interval: float = 0.5) -> None:
        self.pid = pid
        self.output = output
        self.interval = interval
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.sample_count = 0
        self.peak_process_tree_rss_bytes = 0
        self.peak_gpu_memory_mb_by_uuid: dict[str, int] = {}

    def _process(self) -> dict[str, Any]:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return {"psutil_available": False}
        try:
            root = psutil.Process(self.pid)
            processes = [root, *root.children(recursive=True)]
        except psutil.Error:
            return {"psutil_available": True, "root_alive": False}
        rss = 0
        pids: list[int] = []
        for process in processes:
            try:
                rss += int(process.memory_info().rss)
                pids.append(int(process.pid))
            except psutil.Error:
                continue
        self.peak_process_tree_rss_bytes = max(self.peak_process_tree_rss_bytes, rss)
        return {
            "psutil_available": True,
            "root_alive": True,
            "process_tree_rss_bytes": rss,
            "process_ids": pids,
        }

    @staticmethod
    def _gpu() -> list[dict[str, Any]]:
        try:
            text = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,index,name,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5:
                continue
            uuid, index, name, memory_used, utilization = parts
            try:
                rows.append(
                    {
                        "uuid": uuid,
                        "index": int(index),
                        "name": name,
                        "memory_used_mb": int(memory_used),
                        "utilization_gpu_pct": int(utilization),
                    }
                )
            except ValueError:
                continue
        return rows

    def _run(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", encoding="utf-8") as stream:
            while not self.stop.is_set():
                gpu = self._gpu()
                for row in gpu:
                    uuid = str(row["uuid"])
                    self.peak_gpu_memory_mb_by_uuid[uuid] = max(
                        self.peak_gpu_memory_mb_by_uuid.get(uuid, 0),
                        int(row["memory_used_mb"]),
                    )
                stream.write(
                    json.dumps(
                        {
                            "timestamp_monotonic_sec": time.perf_counter(),
                            "process": self._process(),
                            "gpu": gpu,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stream.flush()
                self.sample_count += 1
                self.stop.wait(self.interval)

    def start(self) -> None:
        self.thread.start()

    def finish(self) -> dict[str, Any]:
        self.stop.set()
        self.thread.join(timeout=max(2.0, self.interval * 2))
        return {
            "sample_count": self.sample_count,
            "sample_interval_sec": self.interval,
            "samples_path": str(self.output),
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "peak_gpu_memory_mb_by_uuid": self.peak_gpu_memory_mb_by_uuid,
        }


def _source_commit() -> str | None:
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={PROJECT_ROOT}",
                "-C",
                str(PROJECT_ROOT),
                "rev-parse",
                "HEAD",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def require_runtime() -> None:
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Issue #294 A/B runner must execute inside the production Docker image")
    if PROJECT_ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected project root /workspace, got {PROJECT_ROOT}")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)
    profile = load_homr_profile(PROFILE_NAME)
    validate_profile_runtime(profile)


def _run_process(
    command: list[str],
    *,
    env: dict[str, str],
    log_path: Path,
    samples_path: Path,
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        sampler = ResourceSampler(process.pid, samples_path)
        sampler.start()
        returncode = process.wait()
        resources = sampler.finish()
    wall = time.perf_counter() - started
    result = {
        "command": command,
        "returncode": returncode,
        "wall_sec": wall,
        "log": str(log_path),
        "resources": resources,
    }
    if returncode != 0:
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        raise RuntimeError(
            f"Experiment process failed ({returncode}): {' '.join(command)}\n"
            f"--- log tail ---\n{tail}"
        )
    return result


def _artifact_paths(root: Path, stem: str) -> dict[str, str]:
    run_dir = root / "batch" / stem
    return {
        "detections": str(run_dir / f"{stem}_detections.json"),
        "staff_mask": str(run_dir / f"{stem}_staff_mask.png"),
        "notehead_mask": str(run_dir / f"{stem}_notehead_mask.png"),
    }


def run(images: list[Path], output_root: Path) -> dict[str, Any]:
    require_runtime()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(output_root)
    resolved = [path.resolve() for path in images]
    if not resolved:
        raise ValueError("At least one --image is required")
    if len(set(resolved)) != len(resolved):
        raise ValueError("Duplicate input image")
    for image in resolved:
        if not image.is_file():
            raise FileNotFoundError(image)

    output_root.mkdir(parents=True, exist_ok=False)
    profile = load_homr_profile(PROFILE_NAME)
    profile_env = build_profile_environment(profile)
    pipeline_env = os.environ.copy()
    pipeline_env["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT), pipeline_env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    pages: list[dict[str, Any]] = []
    for index, image in enumerate(resolved, start=1):
        stem = image.stem
        page_root = output_root / f"{index:02d}_{stem}"
        page_root.mkdir(parents=True, exist_ok=False)

        a_root = page_root / "A_pinned"
        a_command = build_profile_command(
            profile,
            images=[image],
            output_root=a_root,
        )
        a_process = _run_process(
            a_command,
            env=profile_env,
            log_path=page_root / "A_pinned.log",
            samples_path=page_root / "A_resources.jsonl",
        )
        a_artifacts = _artifact_paths(a_root, stem)
        for value in a_artifacts.values():
            if not Path(value).is_file():
                raise FileNotFoundError(value)

        b_root = page_root / "B_maintained"
        b_result = page_root / "B_result.json"
        b_command = [
            str(PIPELINE_PYTHON),
            str(PROJECT_ROOT / "tools/issue294/run_maintained_homr_original.py"),
            "--image",
            str(image),
            "--output-root",
            str(b_root),
            "--result",
            str(b_result),
        ]
        b_process = _run_process(
            b_command,
            env=pipeline_env,
            log_path=page_root / "B_maintained.log",
            samples_path=page_root / "B_resources.jsonl",
        )
        if not b_result.is_file():
            raise FileNotFoundError(b_result)
        b_payload = json.loads(b_result.read_text(encoding="utf-8"))
        if not isinstance(b_payload, dict) or b_payload.get("status") != "completed":
            raise ValueError(f"Incomplete maintained-HOMR result: {b_result}")
        if b_payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError("Maintained candidate must not consume historical detector artifacts")
        coordinate_checks = b_payload.get("coordinate_checks")
        if not isinstance(coordinate_checks, dict) or not coordinate_checks.get(
            "masks_match_original_shape"
        ):
            raise ValueError("Maintained candidate masks are not in original-page space")

        a_wall = float(a_process["wall_sec"])
        b_wall = float(b_process["wall_sec"])
        pages.append(
            {
                "image": str(image),
                "A_pinned": {
                    "process": a_process,
                    "artifacts": a_artifacts,
                },
                "B_maintained": {
                    "process": b_process,
                    "result": str(b_result),
                    "worker": b_payload,
                },
                "timing": {
                    "A_wall_sec": a_wall,
                    "B_wall_sec": b_wall,
                    "speedup_A_over_B": a_wall / b_wall if b_wall > 0 else None,
                    "wall_reduction_fraction": (a_wall - b_wall) / a_wall if a_wall > 0 else None,
                },
            }
        )
        (page_root / "page_summary.json").write_text(
            json.dumps(pages[-1], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    a_total = sum(float(page["timing"]["A_wall_sec"]) for page in pages)
    b_total = sum(float(page["timing"]["B_wall_sec"]) for page in pages)
    summary = {
        "schema_version": "issue294.same_original_ab.v1",
        "status": "completed",
        "source_commit": _source_commit(),
        "profile": PROFILE_NAME,
        "process_boundary": "fresh_top_level_process_per_variant_per_page",
        "input_contract": "same_original_page",
        "pages": pages,
        "aggregate_timing": {
            "page_count": len(pages),
            "A_wall_sec": a_total,
            "B_wall_sec": b_total,
            "speedup_A_over_B": a_total / b_total if b_total > 0 else None,
            "wall_reduction_fraction": (a_total - b_total) / a_total if a_total > 0 else None,
            "material_speed_gate_15pct": (
                ((a_total - b_total) / a_total) >= 0.15 if a_total > 0 else False
            ),
        },
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.image, args.output_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": str((args.output_root.resolve() / "summary.json")),
                "aggregate_timing": summary["aggregate_timing"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
