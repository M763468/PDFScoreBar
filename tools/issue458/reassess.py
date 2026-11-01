"""Frozen reassessment matrix; never replaces the original failed contract."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE = "reassessment-20261101"
OUT = ROOT / "logs/issue458" / PHASE
IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"
ORDER = [("b1", 1), ("p1", 2), ("p2", 2), ("b2", 1), ("b3", 1), ("p3", 2), ("p4", 2), ("b4", 1)]


def digest_file(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(path):
    rows = [
        (str(p.relative_to(path)), p.stat().st_size, digest_file(p))
        for p in sorted(path.rglob("*"))
        if p.is_file()
    ]
    return dict(
        files=len(rows),
        bytes=sum(r[1] for r in rows),
        sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
    )


def frozen_source():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True
    )
    if dirty:
        raise RuntimeError("Tracked source is dirty; refusing benchmark")
    names = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "src",
                "configs",
                "models",
                "tools/issue458",
                "tools/issue447",
                "Dockerfile",
                "pyproject.toml",
            ],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    rows = [(p, digest_file(ROOT / p)) for p in names if p]
    return dict(commit=commit, source_sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest())


def cpu_snapshot():
    rows = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            name, rest = raw.split("(", 1)[1].rsplit(")", 1)
            fields = rest.split()
            rows[int(path.name)] = dict(
                name=name,
                ppid=int(fields[1]),
                ticks=int(fields[11]) + int(fields[12]),
                started=fields[19],
            )
        except (OSError, ValueError, IndexError):
            continue
    return rows


def observe_host(directory, stopped):
    old, previous = cpu_snapshot(), time.monotonic()
    hz, streak, competition = os.sysconf("SC_CLK_TCK"), 0, False
    with (directory / "host-cpu.jsonl").open("x") as stream:
        while not stopped.wait(1):
            now, current = time.monotonic(), cpu_snapshot()
            interval = now - previous
            try:
                root_pid = json.loads((directory / "container-inspect.json").read_text())[0][
                    "State"
                ]["Pid"]
            except (OSError, ValueError, KeyError, IndexError):
                root_pid = 0

            def belongs(pid):
                seen = set()
                while pid in current and pid not in seen:
                    if root_pid and pid == root_pid:
                        return True
                    seen.add(pid)
                    pid = current[pid]["ppid"]
                return False

            foreign = []
            for pid, row in current.items():
                prior = old.get(pid)
                if prior and prior["started"] == row["started"] and not belongs(pid):
                    cores = max(0, row["ticks"] - prior["ticks"]) / hz / interval
                    if cores:
                        foreign.append(dict(pid=pid, name=row["name"], cores=cores))
            total = sum(row["cores"] for row in foreign)
            streak = streak + interval if root_pid and total >= 1 else 0
            competition = competition or streak >= 10
            stream.write(
                json.dumps(
                    dict(
                        epoch=time.time(),
                        root_pid=root_pid,
                        unrelated_cores=total,
                        sustained_seconds=streak,
                        top=sorted(foreign, key=lambda r: -r["cores"])[:8],
                    )
                )
                + "\n"
            )
            stream.flush()
            old, previous = current, now
    (directory / "host-competition.json").write_text(
        json.dumps(
            dict(
                persistent_cpu_competition=competition,
                limitation="Linux-visible processes only; WSL/Windows noise and GPU PID attribution may be incomplete",
            )
        )
        + "\n"
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "matrix.json").exists():
        raise FileExistsError("Refusing to overwrite an existing phase")
    source = frozen_source()
    seed = OUT / "seed-primary"
    shutil.copytree(ROOT / "logs/issue458/seed", seed)
    seed.chmod(0o700)
    seed_id = inventory(seed)
    (OUT / "source-seed.json").write_text(
        json.dumps(dict(source=source, seed=seed_id), indent=2) + "\n"
    )
    rows = []

    def run(
        label,
        workers,
        seed_path,
        *,
        score="Shostakovich-Sym5-Va",
        pages="page_01[234].png",
        scope="multi",
        scored=True,
    ):
        assert frozen_source() == source
        cache = OUT / "caches" / label
        shutil.copytree(seed_path, cache)
        cache.chmod(0o700)
        before = inventory(cache)
        assert before == inventory(seed_path)
        directory = OUT / "runs" / label
        directory.mkdir(parents=True, exist_ok=False)
        # The maintained launcher owns creation of this directory. Host observations
        # live separately so its overwrite guard stays intact.
        directory.rmdir()
        observation = OUT / "host" / label
        observation.mkdir(parents=True, exist_ok=False)
        command = [
            sys.executable,
            "tools/issue458/run_experiment.py",
            "--phase",
            PHASE,
            "--label",
            label,
            "--workers",
            str(workers),
            "--scope",
            scope,
            "--score",
            score,
            "--page-glob",
            pages,
            "--exact-shapes",
            "--readonly-source",
            "--image",
            IMAGE,
            "--compile-cache",
            str(cache),
        ]
        stopped = threading.Event()
        # Observe the launcher's inspect through a read alias, without copying logs.
        (observation / "container-inspect.json").symlink_to(directory / "container-inspect.json")
        observer = threading.Thread(target=observe_host, args=(observation, stopped))
        observer.start()
        started = time.time()
        try:
            with (observation / "launcher.log").open("x") as stream:
                process = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        finally:
            stopped.set()
            observer.join()
        assert frozen_source() == source
        row = dict(
            label=label,
            workers=workers,
            score=score,
            pages=pages,
            scored=scored,
            source=source,
            command=command,
            cache_before=before,
            cache_after=inventory(cache),
            start_epoch=started,
            end_epoch=time.time(),
            exit_code=process.returncode,
            noise=json.loads((observation / "host-competition.json").read_text()),
        )
        result = directory / "result.json"
        if result.exists():
            row["result"] = json.loads(result.read_text())
        rows.append(row)
        (OUT / "matrix.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if process.returncode:
            raise RuntimeError(f"{label} failed; retained, no retry/fallback")
        if row["noise"]["persistent_cpu_competition"]:
            raise RuntimeError(
                f"{label} has sustained unrelated CPU work; phase Blocked, no exclusion/retry"
            )
        return cache

    for label, workers in ORDER:
        run("primary-" + label, workers, seed)
    try:
        large_cache = run(
            "large-qualification",
            1,
            seed,
            score="Va_Prokofiev_Symphony1",
            pages="page_00[12].png",
            scored=False,
        )
        large_seed = OUT / "seed-large"
        shutil.copytree(large_cache, large_seed)
        large_seed.chmod(0o700)
        (OUT / "seed-large.json").write_text(json.dumps(inventory(large_seed), indent=2) + "\n")
        for label, workers in [("large-b1", 1), ("large-p1", 2)]:
            run(label, workers, large_seed, score="Va_Prokofiev_Symphony1", pages="page_00[12].png")
    except RuntimeError as error:
        (OUT / "supplemental-status.json").write_text(
            json.dumps(
                {
                    "status": "Failed or Blocked",
                    "reason": str(error),
                    "dependent_runs": "Not run; no retry",
                },
                indent=2,
            )
            + "\n"
        )
    run("single-request2", 2, seed, pages="page_013.png", scope="single", scored=False)


if __name__ == "__main__":
    main()
