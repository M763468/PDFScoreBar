"""PDFScoreBar Windows portable launcher (#535).

Commands (through ``PDFScoreBar.cmd`` in the folder root):

  preflight                 check folder, location, disk, GPU, CUDA sessions
  serve                     browser app: submit PDFs, follow jobs, download, review (#507)
  run <pdf> --output <dir>  process one PDF; deliverables are copied to <dir>
  review <job>              open the correction GUI for a job (save, regenerate, resume)
  verify [--full]           compare the folder with runtime/build_manifest.json

``serve`` and ``run`` share the persistent job root ``<root>\\jobs`` and its lock, so a
browser session and a command-line job never process at the same time.

Jobs are processed under ``<root>\\jobs`` (short ASCII paths for OpenCV/ONNX Runtime
and MAX_PATH); only the finished deliverables are written to the user's output folder,
which may use any characters. Everything mutable (jobs, caches, temporary files, the
generated runtime overlay) stays inside the folder; nothing is installed system-wide.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "app"
PYTHON = ROOT / "python" / "python.exe"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest import load_manifest, verify  # noqa: E402

JOBS = ROOT / "jobs"
# Same pattern as tools/browser_jobs (browser and command-line jobs share the root).
JOB_ID = re.compile(r"job-[0-9a-f]{12,32}")
JOBS_LOCK = ".browser-jobs.lock"

# Internal paths below the root reach about 200 characters (job id, page stems,
# detector subtrees). Keep the root short so every path stays below MAX_PATH (260).
MAX_ROOT_CHARS = 40
MIN_FREE_GIB = 20
MIN_VRAM_GIB = 6


class LauncherError(RuntimeError):
    pass


def child_environment() -> dict[str, str]:
    manifest = load_manifest(ROOT)
    state = ROOT / "state"
    cache = ROOT / "cache"
    for directory in (state, cache / "tmp", ROOT / "jobs"):
        directory.mkdir(parents=True, exist_ok=True)
    overlay = state / "homr_profile_runtime.json"
    overlay.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.homr_profile_runtime.v1",
                "profile": "maintained_original",
                "runtime": {
                    "python": str(PYTHON),
                    "homr_source": str(ROOT / "python" / "Lib" / "site-packages"),
                    "pdfscore_source": str(APP),
                    "homr_commit_marker": str(
                        ROOT / "runtime" / "markers" / "homr_maintained_profile_commit.txt"
                    ),
                    "pdfscore_commit_marker": str(
                        ROOT / "runtime" / "markers" / "pdfscore_maintained_profile_commit.txt"
                    ),
                    "compat_entrypoint": str(
                        APP / "src" / "pipeline" / "detection" / "maintained_homr_worker.py"
                    ),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "PDFSCORE", "TORCH", "TRITON", "CUDA_VISIBLE"))
    }
    env.update(
        {
            "PYTHONPATH": str(APP),
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "PATH": os.pathsep.join([str(ROOT / "python"), env.get("PATH", "")]),
            "PDFSCOREBAR_MODEL_CACHE": str(ROOT / "assets" / "model-cache"),
            "PDFSCORE_LABEL_FONT": str(ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"),
            "PDFSCORE_HOMR_PROFILE_RUNTIME": str(overlay),
            "PDFSCORE_REQUIRE_CUDA_ORT": "1",
            "PDFSCORE_HOST_SOURCE_COMMIT": manifest["source_commit"],
            "PDFSCORE_HOST_SOURCE_BRANCH": "windows-portable",
            "PDFSCORE_HOST_SOURCE_ROOT": str(APP),
            "TORCHINDUCTOR_CACHE_DIR": str(cache / "inductor"),
            "TRITON_CACHE_DIR": str(cache / "triton"),
            "TORCH_HOME": str(cache / "torch"),
            "HF_HOME": str(cache / "hf"),
            "TEMP": str(cache / "tmp"),
            "TMP": str(cache / "tmp"),
        }
    )
    return env


def check_location() -> list[str]:
    problems = []
    if not str(ROOT).isascii():
        problems.append(
            f"The folder path must use ASCII characters only (OpenCV/HOMR limitation): {ROOT}"
        )
    if len(str(ROOT)) > MAX_ROOT_CHARS:
        problems.append(
            f"The folder path is {len(str(ROOT))} characters; move it to a path of at most "
            f"{MAX_ROOT_CHARS} characters, for example C:\\PDFScoreBar"
        )
    free = shutil.disk_usage(ROOT).free / 2**30
    if free < MIN_FREE_GIB:
        problems.append(
            f"Only {free:.1f} GiB free on the folder's drive; {MIN_FREE_GIB} GiB needed"
        )
    return problems


_GPU_PROBE = r"""
import json, sys
import torch
result = {"torch": torch.__version__, "cuda_available": torch.cuda.is_available()}
if result["cuda_available"]:
    props = torch.cuda.get_device_properties(0)
    result.update(gpu=props.name, vram_gib=props.total_memory / 2**30,
                  capability=list(torch.cuda.get_device_capability(0)))
    import onnxruntime as ort
    from pathlib import Path
    import homr
    model = sorted((Path(homr.__file__).parent / "segmentation").glob("*.onnx"))[0]
    session = ort.InferenceSession(str(model), providers=["CUDAExecutionProvider"])
    result["ort_session_providers"] = session.get_providers()
    import triton  # torch.compile reduce-overhead needs triton-windows
    result["triton"] = triton.__version__
print(json.dumps(result))
"""


def check_gpu(env: dict[str, str]) -> tuple[dict, list[str]]:
    completed = subprocess.run(
        [str(PYTHON), "-c", _GPU_PROBE], env=env, cwd=APP, capture_output=True, text=True
    )
    if completed.returncode != 0:
        return {}, [f"GPU/runtime probe failed:\n{completed.stderr.strip()[-2000:]}"]
    info = json.loads(completed.stdout.strip().splitlines()[-1])
    problems = []
    if not info.get("cuda_available"):
        problems.append("No CUDA GPU is visible to PyTorch (NVIDIA GPU and driver required)")
    elif info["vram_gib"] < MIN_VRAM_GIB:
        problems.append(f"GPU has {info['vram_gib']:.1f} GiB VRAM; {MIN_VRAM_GIB} GiB needed")
    elif "CUDAExecutionProvider" not in info.get("ort_session_providers", []):
        problems.append(
            "ONNX Runtime created a CPU session although CUDA was requested "
            f"(providers={info.get('ort_session_providers')})"
        )
    return info, problems


def preflight(*, full_verify: bool = False, gpu: bool = True) -> dict:
    problems = check_location()
    problems += verify(ROOT, full=full_verify)
    report: dict = {"root": str(ROOT), "source_commit": load_manifest(ROOT)["source_commit"]}
    if not problems and gpu:
        info, gpu_problems = check_gpu(child_environment())
        report["gpu"] = info
        problems += gpu_problems
    report["problems"] = problems
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if problems:
        raise LauncherError("Preflight failed")
    return report


def command_run(args: argparse.Namespace) -> int:
    pdf = args.pdf.resolve(strict=True)
    output = args.output.resolve()
    preflight(gpu=True)
    env = child_environment()
    jobs = JOBS
    command = [str(PYTHON), "-m", "docker.distribution_job", str(pdf), "--output", str(jobs)]
    if args.pages:
        command += ["--pages", *map(str, args.pages)]
    with jobs_root_lock():
        before = {path.name for path in jobs.iterdir()}
        status = owned_call(command, env)
    created = sorted({path.name for path in jobs.iterdir()} - before)
    if len(created) != 1:
        print(f"Expected one new job folder, found {created}", file=sys.stderr)
        return status or 1
    job = jobs / created[0]
    output.mkdir(parents=True, exist_ok=True)
    copied = []
    for deliverable in sorted((job / "final").glob("*.pdf")) if status == 0 else []:
        target = output / deliverable.name
        shutil.copyfile(deliverable, target)
        copied.append(str(target))
    pointer = output / f"{job.name}.json"
    # The pointer names the job, not the folder location: the portable folder may be
    # moved, and the job is always resolved below the current root (#535).
    pointer.write_text(
        json.dumps(
            {
                "job": job.name,
                "job_folder_relative": f"jobs/{job.name}",
                "status": status,
                "deliverables": copied,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps({"job": job.name, "status": status, "deliverables": copied}, ensure_ascii=False)
    )
    return status


def _app_module(name: str):
    """Import a stdlib-only helper module of the bundled application."""

    sys.path.insert(0, str(APP))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(APP))


def owned_tree(command: list[str], env: dict[str, str]):
    """Start ``command`` in a kill-on-close Job Object that owns all its descendants.

    Pipeline workers are started with plain subprocess calls; on Linux the container
    reaps them, but on Windows they would outlive a crashed server or job process.
    Job Objects nest, so everything below the child stays in this job: the launcher
    kills what is left when the child exits, and the OS does so if the launcher dies.
    """

    tree_class = _app_module("src.common.process_tree").OwnedProcessTree
    return tree_class(command, env=env, cwd=APP)


def owned_call(command: list[str], env: dict[str, str]) -> int:
    with owned_tree(command, env) as tree:
        try:
            return tree.wait()
        except KeyboardInterrupt:
            return 130


@contextmanager
def jobs_root_lock():
    """Hold the job-root lock that ``tools.browser_jobs`` takes while serving."""

    file_lock = _app_module("src.common.file_lock")
    JOBS.mkdir(parents=True, exist_ok=True)
    with os.fdopen(file_lock.open_lock_file(JOBS / JOBS_LOCK), "rb") as lock:
        try:
            file_lock.lock_exclusive_nonblocking(lock)
        except BlockingIOError as error:
            raise LauncherError(
                "The jobs of this folder are in use by another PDFScoreBar window (serve or "
                "run); stop it first or submit the PDF from the browser"
            ) from error
        yield


def resolve_job(value: str) -> Path:
    """Resolve a job id, job folder or ``<job>.json`` pointer to a job below this root.

    A pointer is resolved by its job id only, so pointers written before the folder was
    moved keep working; absolute paths stored in older pointers are ignored.
    """

    candidate = Path(value)
    if candidate.suffix == ".json" and candidate.is_file():
        try:
            pointer = json.loads(candidate.read_text(encoding="utf-8"))
            job_id = pointer["job"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LauncherError(f"Not a PDFScoreBar job pointer: {value}") from error
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
            raise LauncherError(f"Invalid job id in pointer: {value}")
        candidate = JOBS / job_id
    elif not candidate.is_absolute():
        candidate = JOBS / value
    if candidate.is_symlink() or not JOB_ID.fullmatch(candidate.name):
        raise LauncherError(f"Not a job of this folder: {value}")
    job = candidate.resolve()
    if job.parent != JOBS.resolve() or not job.is_dir():
        raise LauncherError(f"Not a job of this folder: {value}")
    return job


def moved_jobs() -> list[Path]:
    """Prepared jobs whose local review manifest still names a former folder location."""

    stale = []
    for job in sorted(JOBS.iterdir()) if JOBS.is_dir() else []:
        if not JOB_ID.fullmatch(job.name) or job.is_symlink() or not job.is_dir():
            continue
        retained_run = job / ".engine-retained" / "runs" / job.name
        local = retained_run / "local_manifest.json"
        if not local.is_file():
            continue
        try:
            run_dir = json.loads(local.read_text(encoding="utf-8")).get("run_dir")
        except (OSError, ValueError, AttributeError):
            run_dir = None
        if run_dir != str(retained_run):
            stale.append(job)
    return stale


def rebind_moved_jobs(env: dict[str, str]) -> list[str]:
    """Re-run the local review binding for jobs that were moved with the folder."""

    rebound = []
    for job in moved_jobs():
        status = owned_call(
            [str(PYTHON), "-m", "docker.distribution_job", "--prepare-review", str(job)], env
        )
        if status:
            raise LauncherError(f"Could not rebind moved job {job.name} (exit {status})")
        rebound.append(job.name)
    return rebound


def command_review(args: argparse.Namespace) -> int:
    job = resolve_job(args.job)
    check = check_location() + verify(ROOT, full=False)
    if check:
        print("\n".join(check), file=sys.stderr)
        return 2
    env = child_environment()
    status = owned_call(
        [str(PYTHON), "-m", "docker.distribution_job", "--prepare-review", str(job)], env
    )
    if status:
        return status
    handoff = job / "review" / "manual_correction_input.json"
    print(f"Review: http://127.0.0.1:{args.port}/  (Ctrl+C to stop; work is saved in {job})")
    return owned_call(
        [
            str(PYTHON),
            "-m",
            "tools.review_correction.server",
            "--handoff",
            str(handoff),
            "--port",
            str(args.port),
        ],
        env,
    )


def _wait_for_port(port: int, process, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def command_serve(args: argparse.Namespace) -> int:
    preflight(gpu=True)
    env = child_environment()
    with jobs_root_lock():  # refuse early if serve or run already uses the jobs
        rebound = rebind_moved_jobs(env)
    if rebound:
        print(f"Rebound {len(rebound)} moved job(s) to this folder: {', '.join(rebound)}")
    # The browser application is tools/browser_jobs (#507) unchanged; it holds the
    # job-root lock for its whole lifetime.
    command = [
        str(PYTHON),
        "-m",
        "tools.browser_jobs.server",
        "--output",
        str(JOBS),
        "--port",
        str(args.port),
    ]
    # Closing the tree also ends running jobs' workers if the server stops or crashes.
    with owned_tree(command, env) as tree:
        try:
            if _wait_for_port(args.port, tree) and not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{args.port}/")
            return tree.wait()
        except KeyboardInterrupt:
            return 130


def command_verify(args: argparse.Namespace) -> int:
    problems = verify(ROOT, full=args.full)
    print(json.dumps({"root": str(ROOT), "full": args.full, "problems": problems}, indent=2))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="PDFScoreBar.cmd", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("preflight")
    pre.add_argument("--full", action="store_true", help="hash every file (slow)")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8010)
    serve.add_argument("--no-browser", action="store_true", help="do not open a browser")
    run = commands.add_parser("run")
    run.add_argument("pdf", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--pages", type=int, nargs="+")
    review = commands.add_parser("review")
    review.add_argument("job", help="job id, job folder, or the <job>.json written by run")
    review.add_argument("--port", type=int, default=8010)
    ver = commands.add_parser("verify")
    ver.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            preflight(full_verify=args.full)
            return 0
        if args.command == "serve":
            return command_serve(args)
        if args.command == "run":
            return command_run(args)
        if args.command == "review":
            return command_review(args)
        return command_verify(args)
    except (LauncherError, OSError, ValueError) as error:
        print(f"PDFScoreBar: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
