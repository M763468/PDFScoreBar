"""Read-only /proc and cgroup sampler for one dedicated benchmark container.

Run using docker exec as the benchmark UID. This adds no CUDA synchronization.
Process residency is sampled, not exact wall time, and nested workers overlap.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def snapshot() -> dict:
    now = time.monotonic()
    clock_ticks = os.sysconf("SC_CLK_TCK")
    page_size = os.sysconf("SC_PAGE_SIZE")
    processes = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace")
                .strip()
            )
            if "/opt/venv_pipeline/bin/python" not in command:
                continue
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            io = {}
            for line in (entry / "io").read_text().splitlines():
                key, value = line.split(":", 1)
                io[key] = int(value)
            processes.append(
                {
                    "pid": int(entry.name),
                    "ppid": int(fields[1]),
                    "command": command,
                    "start_ticks": int(fields[19]),
                    "cpu_seconds": (int(fields[11]) + int(fields[12])) / clock_ticks,
                    "cpu_user_seconds": int(fields[11]) / clock_ticks,
                    "cpu_system_seconds": int(fields[12]) / clock_ticks,
                    "state": fields[0],
                    "minor_faults": int(fields[7]),
                    "major_faults": int(fields[9]),
                    "rss_bytes": int(fields[21]) * page_size,
                    "io": io,
                }
            )
            try:
                scheduler = [int(v) for v in (entry / "schedstat").read_text().split()]
                processes[-1]["scheduler"] = {
                    "runtime_ns": scheduler[0],
                    "runqueue_wait_ns": scheduler[1],
                    "timeslices": scheduler[2],
                }
                processes[-1]["wait_channel"] = (entry / "wchan").read_text().strip()
            except (OSError, ValueError, IndexError):
                pass
        except (OSError, ValueError, IndexError):
            continue
    cgroup = {}
    for name in ("cpu.stat", "memory.current", "memory.peak", "io.stat"):
        try:
            cgroup[name] = (Path("/sys/fs/cgroup") / name).read_text()
        except OSError:
            pass
    return {
        "monotonic": now,
        "epoch": time.time(),
        "observer_pid": os.getpid(),
        "processes": processes,
        "cgroup": cgroup,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.2)
    args = parser.parse_args()
    if args.interval < 0.05:
        parser.error("interval must be at least 0.05 seconds")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", buffering=1) as stream:
        while True:
            stream.write(json.dumps(snapshot(), separators=(",", ":")) + "\n")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
