"""Bounded disposable source jobs and explicit, conservative admission."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def select_workers(policy, images, *, available_ram_gib, available_vram_gib, device):
    requested = policy.get("workers", 1)
    if type(requested) is not int or requested < 1:
        raise ValueError("source_concurrency.workers must be a positive integer")
    if policy.get("on_unavailable", "error") not in ("error", "serial"):
        raise ValueError("on_unavailable must be error or serial")
    if (
        type(policy.get("validated_workers", 2)) is not int
        or policy.get("validated_workers", 2) < 1
    ):
        raise ValueError("validated_workers must be a positive integer")
    result = dict(
        requested_workers=requested,
        selected_workers=1,
        reason="serial default",
        available_ram_gib=available_ram_gib,
        available_vram_gib=available_vram_gib,
        device=device,
        inputs=[str(p.resolve()) for p in images],
    )
    if requested == 1 or len(images) < 2:
        return result
    # Operators must explicitly supply a validated envelope for their deployment.
    from PIL import Image

    pixels = []
    for path in images:
        with Image.open(path) as image:
            pixels.append(image.width * image.height)
    result["input_pixels"] = pixels
    required = ("ram_gib", "vram_gib", "max_input_pixels", "device")
    reason = "missing explicit resource envelope"
    if all(k in policy for k in required):
        if any(not math.isfinite(float(policy[k])) or float(policy[k]) <= 0 for k in required[:3]):
            raise ValueError("source resource envelope must be positive")
        if requested > policy.get("validated_workers", 2):
            reason = "requested workers exceed validated envelope"
        elif device != policy["device"]:
            reason = "unsupported device"
        elif max(pixels) > policy["max_input_pixels"]:
            reason = "input exceeds validated shape envelope"
        elif available_ram_gib < policy["ram_gib"]:
            reason = "insufficient available RAM"
        elif available_vram_gib < policy["vram_gib"]:
            reason = "insufficient available VRAM"
        else:
            result.update(
                selected_workers=min(requested, len(images)), reason="explicit envelope admitted"
            )
            return result
    if policy.get("on_unavailable", "error") != "serial":
        raise RuntimeError(f"Source concurrency unavailable: {reason}")
    result["reason"] = reason
    return result


def available_resources():
    """Respect both host available memory and remaining cgroup-v2 allowance."""
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    ram = int(mem["MemAvailable"].split()[0]) * 1024
    limit = Path("/sys/fs/cgroup/memory.max")
    if limit.exists() and limit.read_text().strip() != "max":
        ram = min(
            ram, max(0, int(limit.read_text()) - int(limit.with_name("memory.current").read_text()))
        )
    try:
        rows = (
            subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader,nounits"],
                text=True,
                timeout=10,
            )
            .strip()
            .splitlines()
        )
        if len(rows) != 1:
            return ram / 2**30, 0, "unsupported multi-GPU"
        device, free = rows[0].rsplit(",", 1)
        return ram / 2**30, float(free) / 1024, device.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return ram / 2**30, 0, "unknown"


class SourceCancelled(RuntimeError):
    """A sibling failed or the caller cancelled; never replace the original error."""


class SourceJobs:
    def __init__(self, timeout):
        if not 0 < float(timeout) < float("inf"):
            raise ValueError("source timeout must be finite and positive")
        self.timeout = float(timeout)
        self.cancelled = threading.Event()
        self._failure_lock = threading.Lock()
        self.first_error = None

    def _fail(self, error):
        with self._failure_lock:
            if self.first_error is None and not isinstance(error, SourceCancelled):
                self.first_error = error
            self.cancelled.set()

    def run(self, command, **kwargs):
        if self.cancelled.is_set():
            raise SourceCancelled("Source jobs cancelled")
        process = subprocess.Popen(command, start_new_session=True, **kwargs)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if self.cancelled.wait(0.05):
                    raise SourceCancelled("Source jobs cancelled")
                if time.monotonic() - started > self.timeout:
                    raise TimeoutError(f"Source job timeout: {command}")
            return subprocess.CompletedProcess(command, process.returncode)
        except BaseException as error:
            self._fail(error)
            raise
        finally:
            # Kill the entire session group, including descendants after leader exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    def ordered(self, keys, execute, workers, events):
        keys = list(keys)
        if len({str(k.resolve()) for k in keys}) != len(keys):
            raise ValueError("Duplicate source inputs")
        pending = deque()
        iterator = iter(keys)
        events.parent.mkdir(parents=True, exist_ok=True)

        def job(key):
            try:
                if self.cancelled.is_set():
                    raise SourceCancelled("Source jobs cancelled before start")
                return execute(key)
            except BaseException as error:
                self._fail(error)
                raise

        previous_handler = None
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.getsignal(signal.SIGTERM)

            def terminate(signum, frame):
                self.cancelled.set()
                raise SystemExit(128 + signum)

            signal.signal(signal.SIGTERM, terminate)
        try:
            yield from self._ordered_pool(keys, execute, workers, events, job, pending, iterator)
        finally:
            if previous_handler is not None:
                signal.signal(signal.SIGTERM, previous_handler)

    def _ordered_pool(self, keys, execute, workers, events, job, pending, iterator):
        with ThreadPoolExecutor(max_workers=workers) as executor:
            try:
                for key in list(keys)[:workers]:
                    next(iterator)
                    pending.append((key, executor.submit(job, key)))
                while pending:
                    key, future = pending.popleft()
                    try:
                        result = future.result()
                    except SourceCancelled:
                        if self.first_error is not None:
                            raise self.first_error
                        raise
                    with events.open("a") as stream:
                        stream.write(json.dumps({"consumed": str(key), "time": time.time()}) + "\n")
                    yield key, result
                    key = next(iterator, None)
                    if key is not None:
                        pending.append((key, executor.submit(job, key)))
            finally:
                self.cancelled.set()
                for _, future in pending:
                    future.cancel()
