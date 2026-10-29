"""Research-only source scheduling shim; production modules are never edited.

Both controls use the same ordered consumer. SR still finishes and exits first.
Each source job remains a disposable Python process with its existing contracts.
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")


class OrderedJobs:
    def __init__(self, keys, execute, workers: int, events: Path | None = None):
        if workers not in (1, 2):
            raise ValueError("only bounded 1/2-worker experiments are supported")
        self.events = events
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.futures = {}
        for index, key in enumerate(keys):
            submitted = time.perf_counter()
            self.futures[key] = self.executor.submit(self._execute, execute, key, index, submitted)

    def _write(self, payload):
        if self.events is not None:
            with self.lock:
                with self.events.open("a") as stream:
                    stream.write(json.dumps(payload) + "\n")

    def _execute(self, execute, key, index, submitted):
        started = time.perf_counter()
        self._write(
            {
                "event": "start",
                "image": str(key),
                "index": index,
                "submitted": submitted,
                "started": started,
            }
        )
        success = False
        try:
            result = execute(key)
            success = True
            return result
        finally:
            self._write(
                {
                    "event": "end",
                    "image": str(key),
                    "index": index,
                    "started": started,
                    "ended": time.perf_counter(),
                    "success": success,
                }
            )

    def result(self, key):
        started = time.perf_counter()
        result = self.futures[key].result()
        self._write(
            {
                "event": "consume",
                "image": str(key),
                "wait_started": started,
                "consumed": time.perf_counter(),
            }
        )
        return result

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def install_source_prefetch(workers: int, events: Path | None = None, detector_class=None):
    if detector_class is None:
        from src.pipeline.detection.profile_sources_batch_sr import BatchSRProfileHybridDetector

        detector_class = BatchSRProfileHybridDetector
    original = detector_class._source_page_worker

    def source(self, *, image, worker_output, baseline_output, support_output, precomputed_sr):
        state = getattr(self, "_issue447_ordered_jobs", None)
        if state is None:
            # The production caller sets this only after the all-pages SR process exits.
            payload = self._last_sr_batch_result
            if not payload or payload.get("status") != "completed":
                raise RuntimeError("prefetch requires completed production SR batch")
            by_image = {Path(item["image"]).resolve(): item for item in payload["outputs"]}
            if any(key.resolve() not in by_image for key in self.images):
                raise ValueError("SR batch does not cover the ordered source input")

            def execute(key):
                return original(
                    self,
                    image=key,
                    worker_output=worker_output,
                    baseline_output=baseline_output,
                    support_output=support_output,
                    precomputed_sr=by_image[key.resolve()],
                )

            state = OrderedJobs(self.images, execute, workers, events)
            self._issue447_ordered_jobs = state
        try:
            result = state.result(image)
        except BaseException:
            state.close()
            del self._issue447_ordered_jobs
            raise
        if image == self.images[-1]:
            state.close()
            del self._issue447_ordered_jobs
        return result

    detector_class._source_page_worker = source


def component_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-component", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    reference = Path("logs/issue447/runs/multi-off-warm/pipeline/hybrid_output/pipeline")
    pages = ["page_012", "page_014"]
    jobs = {}
    for page in pages:
        request = json.loads(
            (
                reference / "source_page_workers/Shostakovich-Sym5-Va" / page / "request.json"
            ).read_text()
        )
        request["baseline_output"] = str((args.output / "baseline").resolve())
        request["support_output"] = str((args.output / "current_support").resolve())
        request_path = args.output / f"request-{page}.json"
        request_path.write_text(json.dumps(request, indent=2) + "\n")
        jobs[page] = [
            sys.executable,
            "-m",
            "src.pipeline.detection.maintained_source_page_worker",
            "--request",
            str(request_path),
            "--result",
            str(args.output / f"result-{page}.json"),
        ]

    def execute(page):
        with (args.output / f"worker-{page}.log").open("w") as stream:
            process = subprocess.run(jobs[page], stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError(f"source worker failed: {page}, exit {process.returncode}")
        return json.loads((args.output / f"result-{page}.json").read_text())

    started = time.perf_counter()
    pool = OrderedJobs(pages, execute, args.workers, args.output / "source-schedule.jsonl")
    try:
        results = [pool.result(page) for page in pages]
    finally:
        pool.close()
    result = {
        "status": "completed",
        "workers": args.workers,
        "pages": pages,
        "component_wall_seconds": time.perf_counter() - started,
        "ordered_results": [r["image"] for r in results],
        "scope": "same-harness component comparison; retained SR; not E2E",
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    if "--source-component" in sys.argv:
        component_main()
    else:
        if os.environ.get("ISSUE447_OMR_REUSE") == "1":
            from tools.issue447.omr_reuse_poc import install

            install()
        workers = int(os.environ["ISSUE447_SOURCE_WORKERS"])
        events_value = os.environ.get("ISSUE447_SOURCE_EVENTS")
        install_source_prefetch(workers, Path(events_value) if events_value else None)
        runpy.run_module("src.pipeline.main", run_name="__main__", alter_sys=True)
