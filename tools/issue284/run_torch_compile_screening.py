"""Run fresh-process PyTorch 2.13 compile screening for Issue #284 and build one share ZIP."""

from __future__ import annotations

import argparse
import json
import os
import shutil
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
DEFAULT_MODES = ("eager", "default", "reduce-overhead")


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 compile screening requires canonical /workspace container")
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


def _bundle(output: Path, paths: list[Path]) -> Path:
    bundle = output / "issue284_torch_compile_screening_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return bundle


def _steady_stats(payload: dict[str, Any]) -> dict[str, Any]:
    iterations = payload.get("iterations") or []
    walls = [float(item["wall_sec"]) for item in iterations if item.get("wall_sec") is not None]
    steady = walls[1:]
    comparisons = [item.get("comparison") or {} for item in iterations]
    return {
        "first_page_wall_sec": walls[0] if walls else None,
        "steady_page_wall_sec_median": statistics.median(steady) if steady else None,
        "all_pages_byte_identical": bool(comparisons)
        and all(bool(item.get("array_equal")) for item in comparisons),
    }


def _fresh_runtime_dirs(output: Path, mode: str) -> dict[str, Path]:
    roots = {
        "home": output / f"runtime_home_{mode}",
        "inductor": output / f"inductor_cache_{mode}",
        "triton": output / f"triton_cache_{mode}",
        "xdg": output / f"xdg_cache_{mode}",
    }
    for path in roots.values():
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    return roots


def _cleanup_runtime_dirs(runtime_dirs: dict[str, Path]) -> None:
    for path in runtime_dirs.values():
        if path.exists():
            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout-sec", type=float, default=600.0)
    parser.add_argument("--modes", nargs="+", default=list(DEFAULT_MODES))
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

    for mode in args.modes:
        result_path = output / f"{mode}.json"
        log_path = output / f"{mode}.console.log"
        runtime_dirs = _fresh_runtime_dirs(output, mode)

        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_torch_compile_variant.py"),
            "--mode",
            mode,
            "--reference-image",
            str(reference),
            "--result",
            str(result_path),
            "--iterations",
            str(args.iterations),
        ]
        env = dict(os.environ)
        env["HOME"] = str(runtime_dirs["home"])
        env["XDG_CACHE_HOME"] = str(runtime_dirs["xdg"])
        env["TORCHINDUCTOR_CACHE_DIR"] = str(runtime_dirs["inductor"])
        env["TRITON_CACHE_DIR"] = str(runtime_dirs["triton"])

        started = time.perf_counter()
        timed_out = False
        returncode: int | None = None
        with log_path.open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
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
            "mode": mode,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": process_wall,
            "status": payload.get("status") if payload else ("timeout" if timed_out else "missing"),
            "result": str(result_path),
            "log": str(log_path),
            "runtime_dirs": {key: str(value) for key, value in runtime_dirs.items()},
            "runtime_dirs_cleaned": True,
        }
        if payload:
            record.update(_steady_stats(payload))
            record["compile_wrap_sec"] = payload.get("compile_wrap_sec")
            record["memory"] = payload.get("memory")
            record["dynamo_counters"] = payload.get("dynamo_counters")
        records.append(record)
        share_paths.extend([result_path, log_path])
        _cleanup_runtime_dirs(runtime_dirs)

    eager = next((item for item in records if item["mode"] == "eager"), None)
    eager_steady = eager.get("steady_page_wall_sec_median") if eager else None
    for record in records:
        steady = record.get("steady_page_wall_sec_median")
        if eager_steady and steady:
            record["steady_speedup_vs_eager"] = float(eager_steady) / float(steady)
            record["steady_reduction_pct_vs_eager"] = (
                1.0 - float(steady) / float(eager_steady)
            ) * 100.0
        else:
            record["steady_speedup_vs_eager"] = None
            record["steady_reduction_pct_vs_eager"] = None

    eligible = [
        item
        for item in records
        if item.get("status") == "completed"
        and item.get("all_pages_byte_identical")
        and item.get("steady_page_wall_sec_median") is not None
    ]
    fastest = (
        min(eligible, key=lambda item: float(item["steady_page_wall_sec_median"]))
        if eligible
        else None
    )

    summary = {
        "schema_version": "issue284.torch_compile_screening.v3",
        "torch_target": "2.13 stable only",
        "candidate_summary": str(candidate_summary),
        "reference_image": str(reference),
        "iterations_per_mode": args.iterations,
        "timeout_sec": args.timeout_sec,
        "modes": list(args.modes),
        "runs": records,
        "fastest_byte_identical_mode": fastest.get("mode") if fastest else None,
        "decision_rule": (
            "Promote a compile mode only if steady-state is materially faster than eager, "
            "output remains byte-identical in screening, and first-page compile cost can be "
            "amortized by the persistent multi-page SR worker."
        ),
    }
    summary_path = output / "torch_compile_screening_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    share_paths.append(summary_path)
    bundle = _bundle(output, share_paths)

    print(json.dumps(summary, indent=2, default=str))
    print(f"share_bundle={bundle}")
    all_requested_completed = len(records) == len(args.modes) and all(
        item.get("status") == "completed" for item in records
    )
    return 0 if all_requested_completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
