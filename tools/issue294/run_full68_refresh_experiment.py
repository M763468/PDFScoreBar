#!/usr/bin/env python3
"""Safely orchestrate the remaining Issue #294 full68 experiment.

This is temporary experiment-only code.  Unlike an interactive ``set -e`` shell
recipe, every stage is caught and recorded.  By default this driver always exits
with process status 0, even when an experiment stage fails, so a diagnostic
failure cannot terminate an interactive shell that happens to have ``errexit``
enabled.  Use ``--strict-exit`` only when non-zero process status is desired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_downstream_candidate_matrix_full68_host as full68_host
from tools.issue294 import run_same_original_ab_host as base

CONTAINER = "pdfscore_issue294_profile_worktree"
EXPECTED_IMAGE_ID = "sha256:5e1265263a5ba014814002c02fcfaf7f07a61e7000c13697db6c3087c7d2acdc"
BRANCH = "perf/issue294-homr-baseline-refresh"
LATEST_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"
WEIGHT_RELATIVE = Path("external/realesrgan/weights/RealESRGAN_x4plus.pth")
EXPECTED_WEIGHT_SIZE = 67040989
EXPECTED_WEIGHT_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture(command: list[str], *, cwd: Path = PROJECT_ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout.strip()


def _run_visible(command: list[str], *, cwd: Path = PROJECT_ROOT) -> int:
    """Run a long command with live output and return its status without raising."""

    completed = subprocess.run(command, cwd=cwd, check=False)
    return int(completed.returncode)


def _docker_capture(arguments: list[str]) -> str:
    return _capture(["docker", *arguments])


def _docker_test_file(path: str) -> None:
    completed = subprocess.run(
        ["docker", "exec", CONTAINER, "test", "-f", path],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise FileNotFoundError(f"Container file is missing: {path}")


def _exit_code(status: str, strict_exit: bool) -> int:
    return 1 if strict_exit and status != "completed" else 0


def _checkout_step() -> dict[str, Any]:
    branch = _capture(["git", "branch", "--show-current"])
    if branch != BRANCH:
        raise RuntimeError(f"Expected branch {BRANCH}, got {branch or '<detached>'}")
    status = _capture(["git", "status", "--porcelain"])
    if status:
        raise RuntimeError("Issue #294 experiment requires a clean tracked checkout:\n" + status)
    head = _capture(["git", "rev-parse", "HEAD"])
    remote = _capture(["git", "rev-parse", f"origin/{BRANCH}"])
    if head != remote:
        raise RuntimeError(
            f"Local branch is not at remote HEAD: local={head} remote={remote}. "
            f"Run git pull --ff-only origin {BRANCH} and retry."
        )
    return {"branch": branch, "head": head, "remote_head": remote}


def _container_step() -> dict[str, Any]:
    running = _docker_capture(["inspect", "--format", "{{.State.Running}}", CONTAINER])
    if running != "true":
        raise RuntimeError(f"Container is not running: {CONTAINER}")
    image_id = _docker_capture(["inspect", "--format", "{{.Image}}", CONTAINER])
    if image_id != EXPECTED_IMAGE_ID:
        raise RuntimeError(f"Unexpected profiling image: {image_id}")

    token = uuid.uuid4().hex
    host_to_container = PROJECT_ROOT / f".issue294_bind_probe_host_{os.getpid()}"
    container_to_host = PROJECT_ROOT / f".issue294_bind_probe_container_{os.getpid()}"
    try:
        host_to_container.write_text(token + "\n", encoding="utf-8")
        seen = _docker_capture(["exec", CONTAINER, "cat", f"/workspace/{host_to_container.name}"])
        if seen != token:
            raise RuntimeError(
                "Host -> /workspace bind round-trip failed. Do not start full68 while the "
                "Docker Desktop WSL bind is stale."
            )
        _capture(
            [
                "docker",
                "exec",
                CONTAINER,
                "/bin/sh",
                "-c",
                f"printf '%s\\n' '{token}' > '/workspace/{container_to_host.name}'",
            ]
        )
        if not container_to_host.is_file() or container_to_host.read_text(encoding="utf-8").strip() != token:
            raise RuntimeError(
                "Container -> host /workspace bind round-trip failed. The current host wrappers "
                "cannot checkpoint safely until the bind is repaired/recreated."
            )
    finally:
        host_to_container.unlink(missing_ok=True)
        container_to_host.unlink(missing_ok=True)
        subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER,
                "rm",
                "-f",
                f"/workspace/{host_to_container.name}",
                f"/workspace/{container_to_host.name}",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {"container": CONTAINER, "image_id": image_id, "workspace_roundtrip": True}


def _sync_source_step() -> dict[str, Any]:
    producer = subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert producer.stdout is not None
    consumer = subprocess.Popen(
        ["docker", "exec", "-i", CONTAINER, "tar", "-xf", "-", "-C", "/workspace"],
        cwd=PROJECT_ROOT,
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    producer.stdout.close()
    consumer_stdout, consumer_stderr = consumer.communicate()
    producer_stderr = producer.stderr.read() if producer.stderr is not None else b""
    producer_rc = producer.wait()
    if producer_rc != 0 or consumer.returncode != 0:
        raise RuntimeError(
            "Tracked source tar sync failed: "
            f"git_archive_rc={producer_rc} docker_tar_rc={consumer.returncode}\n"
            f"git stderr={producer_stderr.decode(errors='replace')}\n"
            f"docker stdout={consumer_stdout.decode(errors='replace')}\n"
            f"docker stderr={consumer_stderr.decode(errors='replace')}"
        )

    paths = [
        "tools/issue294/run_full68_refresh_experiment.py",
        "tools/issue294/run_fixed_support_smoke.py",
        "tools/issue294/run_downstream_candidate_matrix.py",
        "tools/issue294/run_downstream_candidate_matrix_full68_host.py",
        "tools/issue294/run_full68_mmr_audit.py",
    ]
    hashes: dict[str, dict[str, str]] = {}
    for relative in paths:
        host_path = PROJECT_ROOT / relative
        host_hash = _sha256(host_path)
        container_hash = _docker_capture(["exec", CONTAINER, "sha256sum", f"/workspace/{relative}"]).split()[0]
        if host_hash != container_hash:
            raise RuntimeError(f"Source sync SHA mismatch for {relative}")
        hashes[relative] = {"host": host_hash, "container": container_hash}
    return {"verified_files": hashes}


def _find_weight() -> Path:
    override = os.environ.get("ISSUE294_REALESRGAN_WEIGHT")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(PROJECT_ROOT / WEIGHT_RELATIVE)
    candidates.append(PROJECT_ROOT.parent / "ws_PDFScoreBar" / WEIGHT_RELATIVE)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.stat().st_size != EXPECTED_WEIGHT_SIZE:
            continue
        if _sha256(candidate) != EXPECTED_WEIGHT_SHA256:
            continue
        return candidate.resolve()
    raise FileNotFoundError(
        "Could not find the verified RealESRGAN_x4plus.pth. Checked: "
        + ", ".join(str(path) for path in candidates)
    )


def _weight_step() -> dict[str, Any]:
    weight = _find_weight()
    _capture(["docker", "exec", CONTAINER, "mkdir", "-p", "/workspace/external/realesrgan/weights"])
    copied = subprocess.run(
        [
            "docker",
            "cp",
            str(weight),
            f"{CONTAINER}:/workspace/external/realesrgan/weights/RealESRGAN_x4plus.pth",
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if copied.returncode != 0:
        raise RuntimeError(f"docker cp failed for {weight}")
    container_hash = _docker_capture(
        [
            "exec",
            CONTAINER,
            "sha256sum",
            "/workspace/external/realesrgan/weights/RealESRGAN_x4plus.pth",
        ]
    ).split()[0]
    if container_hash != EXPECTED_WEIGHT_SHA256:
        raise RuntimeError(f"Container Real-ESRGAN weight SHA mismatch: {container_hash}")
    return {
        "host_weight": str(weight),
        "size": weight.stat().st_size,
        "sha256": container_hash,
    }


def _input_preflight_step(latest_commit: str) -> dict[str, Any]:
    required_container_files = [
        "/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
        "/workspace/tools/mmr_training/models/mmr_classifier_best.pth",
    ]
    for path in required_container_files:
        _docker_test_file(path)

    mappings = full68_host._canonical_mappings()
    missing_host_images = [str(item["image"]) for item in mappings if not Path(str(item["image"])).is_file()]
    if missing_host_images:
        raise FileNotFoundError("Missing canonical host images: " + repr(missing_host_images))

    rc = _run_visible(
        [
            sys.executable,
            "tools/issue294/run_downstream_candidate_matrix_host.py",
            "--preflight-only",
            "--latest-homr-commit",
            latest_commit,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"B/C detector-only preflight failed with return code {rc}")
    return {"canonical_pages": len(mappings), "detector_preflight_returncode": rc}


def _tests_step() -> dict[str, Any]:
    tests = [
        "tests/test_issue294_full68_host.py",
        "tests/test_issue294_full68_mmr_audit.py",
        "tests/test_issue294_downstream_candidate_matrix.py",
        "tests/test_issue294_global_page_host.py",
        "tests/test_issue294_full68_refresh_experiment.py",
    ]
    command = [
        "docker",
        "exec",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        CONTAINER,
        "/opt/venv_pipeline/bin/python",
        "-m",
        "pytest",
        *tests,
    ]
    rc = _run_visible(command)
    if rc != 0:
        raise RuntimeError(f"Issue #294 targeted tests failed with return code {rc}")
    return {"tests": tests, "returncode": rc}


def _smoke_step(run_tag: str) -> dict[str, Any]:
    root = f"/workspace/temp/{run_tag}_fixed_support_smoke"
    report = PROJECT_ROOT / "temp" / f"{run_tag}_fixed_support_smoke" / "smoke_report.json"
    if report.is_file():
        payload = _load_json(report)
        if isinstance(payload, dict) and payload.get("status") == "completed":
            return {"reused": True, "report": str(report), "checks": payload.get("checks")}
    rc = _run_visible(
        [
            "docker",
            "exec",
            "-w",
            "/workspace",
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            "/opt/venv_pipeline/bin/python",
            "tools/issue294/run_fixed_support_smoke.py",
            "--image",
            "/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            "--output-root",
            root,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"Fixed-support smoke failed with return code {rc}")
    if not report.is_file():
        raise FileNotFoundError(report)
    payload = _load_json(report)
    if payload.get("status") != "completed":
        raise RuntimeError(f"Fixed-support smoke did not complete: {payload}")
    return {"reused": False, "report": str(report), "checks": payload.get("checks")}


def _semantic_differences(manifest: dict[str, Any]) -> dict[str, Any]:
    semantic: list[dict[str, Any]] = []
    count_only: list[dict[str, Any]] = []
    for page in manifest.get("pages", []):
        native = page["candidate_native_geometry"]
        for label in ("B", "C"):
            comparison = native[f"{label}_vs_A"]
            item = {
                "global_page_id": page["global_page_id"],
                "score": page["score"],
                "page_name": page["page_name"],
                "label": label,
                "comparison": comparison,
            }
            if not (
                comparison["total_measures_equal"]
                and comparison["system_measure_topology_equal"]
                and comparison["numbering_equal"]
            ):
                semantic.append(item)
            elif not comparison["final_barline_count_equal"]:
                count_only.append(item)
    return {"semantic": semantic, "count_only": count_only}


def _full68_step(run_tag: str, latest_commit: str, chunk_size: int) -> dict[str, Any]:
    rc = _run_visible(
        [
            sys.executable,
            "tools/issue294/run_downstream_candidate_matrix_full68_host.py",
            "--run-tag",
            run_tag,
            "--latest-homr-commit",
            latest_commit,
            "--chunk-size",
            str(chunk_size),
        ]
    )
    manifest_path = PROJECT_ROOT / "logs/issue294" / run_tag / "full68_host.json"
    if not manifest_path.is_file():
        raise RuntimeError(
            f"full68 runner returned {rc} without a manifest: {manifest_path}"
        )
    manifest = _load_json(manifest_path)
    if manifest.get("status") != "completed" or int(manifest.get("completed_page_count", 0)) != 68:
        raise RuntimeError(
            f"full68 did not complete 68/68 pages (runner rc={rc}): "
            f"status={manifest.get('status')} pages={manifest.get('completed_page_count')}"
        )
    return {
        "runner_returncode": rc,
        "manifest": str(manifest_path),
        "gates": manifest.get("gates"),
        "differences": _semantic_differences(manifest),
    }


def _mmr_output_path(run_tag: str) -> tuple[Path, bool]:
    root = PROJECT_ROOT / "logs/issue294" / run_tag
    for index in range(1, 100):
        candidate = root / f"full68_mmr_audit_{index:02d}.json"
        if not candidate.exists():
            return candidate, False
        try:
            payload = _load_json(candidate)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict) and payload.get("status") == "completed":
            return candidate, True
    raise RuntimeError("Could not allocate an Issue #294 full68 MMR report path")


def _mmr_step(run_tag: str) -> dict[str, Any]:
    output, reused = _mmr_output_path(run_tag)
    if reused:
        payload = _load_json(output)
        return {
            "reused": True,
            "runner_returncode": None,
            "report": str(output),
            "runtime": payload.get("runtime"),
            "gates": payload.get("gates"),
            "comparisons": payload.get("comparisons"),
        }

    manifest_container = f"/workspace/logs/issue294/{run_tag}/full68_host.json"
    output_container = f"/workspace/logs/issue294/{run_tag}/{output.name}"
    rc = _run_visible(
        [
            "docker",
            "exec",
            "-w",
            "/workspace",
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            "/opt/venv_pipeline/bin/python",
            "tools/issue294/run_full68_mmr_audit.py",
            "--full68-manifest",
            manifest_container,
            "--output",
            output_container,
        ]
    )
    if not output.is_file():
        raise RuntimeError(f"MMR runner returned {rc} without report: {output}")
    payload = _load_json(output)
    if payload.get("status") != "completed":
        raise RuntimeError(f"MMR audit did not complete (runner rc={rc}): {payload}")
    return {
        "reused": False,
        "runner_returncode": rc,
        "report": str(output),
        "runtime": payload.get("runtime"),
        "gates": payload.get("gates"),
        "comparisons": payload.get("comparisons"),
    }


def run_experiment(*, run_tag: str, latest_commit: str, chunk_size: int) -> dict[str, Any]:
    report_path = PROJECT_ROOT / "logs/issue294" / f"{run_tag}_experiment_driver.json"
    payload: dict[str, Any] = {
        "schema_version": "issue294.full68_refresh_experiment.v1",
        "status": "in_progress",
        "run_tag": run_tag,
        "latest_homr_commit": latest_commit,
        "started_unix": time.time(),
        "steps": [],
    }

    def record() -> None:
        _write_json(report_path, payload)

    def step(name: str, function: Callable[[], dict[str, Any]]) -> bool:
        print(f"\n=== {name} ===", flush=True)
        started = time.perf_counter()
        try:
            detail = function()
        except Exception as error:  # noqa: BLE001
            elapsed = time.perf_counter() - started
            row = {
                "name": name,
                "status": "failed",
                "elapsed_sec": elapsed,
                "error_type": type(error).__name__,
                "error": str(error),
            }
            payload["steps"].append(row)
            payload["status"] = "failed"
            payload["failed_step"] = name
            payload["finished_unix"] = time.time()
            record()
            print(json.dumps(row, indent=2, ensure_ascii=False), flush=True)
            print(
                "Experiment stopped safely. The shell process will return 0 by default; "
                f"inspect {report_path}",
                flush=True,
            )
            return False
        elapsed = time.perf_counter() - started
        row = {"name": name, "status": "completed", "elapsed_sec": elapsed, "detail": detail}
        payload["steps"].append(row)
        record()
        print(json.dumps(row, indent=2, ensure_ascii=False), flush=True)
        return True

    stages: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("checkout", _checkout_step),
        ("container_workspace_roundtrip", _container_step),
        ("sync_tracked_source", _sync_source_step),
        ("sync_realesrgan_weight", _weight_step),
        ("input_and_detector_preflight", lambda: _input_preflight_step(latest_commit)),
        ("targeted_tests", _tests_step),
        ("fixed_support_smoke", lambda: _smoke_step(run_tag)),
        ("full68_correctness", lambda: _full68_step(run_tag, latest_commit, chunk_size)),
        ("full68_batched_mmr", lambda: _mmr_step(run_tag)),
    ]
    for name, function in stages:
        if not step(name, function):
            return payload

    payload["status"] = "completed"
    payload["finished_unix"] = time.time()
    record()
    print(f"\nExperiment execution completed. Driver report: {report_path}", flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default="issue294_full68_refresh_02")
    parser.add_argument("--latest-homr-commit", default=LATEST_COMMIT)
    parser.add_argument("--chunk-size", type=int, default=6)
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Return non-zero when a driver stage fails. Default is always zero for interactive safety.",
    )
    args = parser.parse_args()
    payload = run_experiment(
        run_tag=args.run_tag,
        latest_commit=args.latest_homr_commit,
        chunk_size=args.chunk_size,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "failed_step": payload.get("failed_step"),
                "process_exit_policy": "strict" if args.strict_exit else "always_zero",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return _exit_code(str(payload["status"]), args.strict_exit)


if __name__ == "__main__":
    raise SystemExit(main())
