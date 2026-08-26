"""Run Issue #284 torch.compile screening in a disposable compiler-enabled container.

The production image/container is not mutated. This host-side wrapper starts a
temporary container from the exact image used by ``pdfscore_pipeline_pytest_dev``,
reuses that container's mounts, installs only the build toolchain required by
Triton/Inductor into the temporary container overlay, runs the existing screening
as the invoking host UID/GID, then removes the temporary container.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTAINER = "pdfscore_pipeline_pytest_dev"


def _run(
    command: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def _require_host_repo() -> None:
    if Path("/.dockerenv").exists():
        raise RuntimeError("This wrapper must run on the host, not inside Docker")
    if not (ROOT / ".git").exists():
        raise RuntimeError(f"Expected repository root, got {ROOT}")


def _container_image(container: str) -> str:
    completed = _run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container],
        capture_output=True,
    )
    image = completed.stdout.strip()
    if not image:
        raise RuntimeError(f"Could not resolve image for container {container}")
    return image


def _append_metadata_to_bundle(output: Path, metadata_path: Path) -> None:
    bundle = output / "issue284_torch_compile_screening_bundle.zip"
    if not bundle.is_file() or not metadata_path.is_file():
        return
    with zipfile.ZipFile(bundle, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(metadata_path, arcname=metadata_path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout-sec", type=float, default=600.0)
    args = parser.parse_args()

    _require_host_repo()

    output = args.output.resolve()
    if not output.is_dir():
        raise FileNotFoundError(
            f"Output directory must be created on the host before running: {output}"
        )
    if any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    if not os.access(output, os.W_OK | os.X_OK):
        raise PermissionError(f"Output is not writable by the invoking user: {output}")

    candidate_summary = args.candidate_summary.resolve()
    if not candidate_summary.is_file():
        raise FileNotFoundError(candidate_summary)

    uid = os.getuid()
    gid = os.getgid()
    base_image = _container_image(args.container)
    temporary_container = f"pdfscore-issue284-compile-probe-{uid}-{int(time.time())}"

    metadata_path = output / "compiler_probe_environment.json"
    metadata = {
        "schema_version": "issue284.compile_probe_environment.v2",
        "base_container": args.container,
        "base_image": base_image,
        "temporary_container": temporary_container,
        "host_uid": uid,
        "host_gid": gid,
        "candidate_summary": str(candidate_summary),
        "output": str(output),
        "toolchain_packages": ["build-essential", "python3.11-dev"],
    }

    container_output = "/workspace/" + str(output.relative_to(ROOT)).replace(os.sep, "/")
    container_summary = "/workspace/" + str(candidate_summary.relative_to(ROOT)).replace(
        os.sep, "/"
    )

    create_command = [
        "docker",
        "run",
        "--detach",
        "--gpus",
        "all",
        "--volumes-from",
        args.container,
        "--user",
        "0:0",
        "--workdir",
        "/workspace",
        "--name",
        temporary_container,
        base_image,
        "sleep",
        "infinity",
    ]

    install_command = [
        "docker",
        "exec",
        "--user",
        "0:0",
        temporary_container,
        "bash",
        "-lc",
        (
            "apt-get update && "
            "apt-get install -y --no-install-recommends build-essential python3.11-dev && "
            "rm -rf /var/lib/apt/lists/*"
        ),
    ]

    screening_command = [
        "docker",
        "exec",
        "--user",
        f"{uid}:{gid}",
        "--workdir",
        "/workspace",
        "--env",
        "CC=/usr/bin/gcc",
        "--env",
        "CXX=/usr/bin/g++",
        temporary_container,
        "/opt/venv_pipeline/bin/python",
        "tools/issue284/run_torch_compile_screening.py",
        "--candidate-summary",
        container_summary,
        "--output",
        container_output,
        "--iterations",
        str(args.iterations),
        "--timeout-sec",
        str(args.timeout_sec),
    ]

    print(f"base_image={base_image}")
    print(f"temporary_container={temporary_container}")
    print("Starting disposable container:")
    print(" ".join(shlex.quote(item) for item in create_command))

    returncode = 1
    container_started = False
    try:
        created = _run(create_command, check=False)
        metadata["container_start_returncode"] = created.returncode
        if created.returncode != 0:
            return created.returncode
        container_started = True

        print("Installing compiler toolchain in temporary container...")
        installed = _run(install_command, check=False)
        metadata["toolchain_install_returncode"] = installed.returncode
        if installed.returncode != 0:
            return installed.returncode

        print("Running screening:")
        print(" ".join(shlex.quote(item) for item in screening_command))
        completed = _run(screening_command, check=False)
        metadata["screening_returncode"] = completed.returncode
        returncode = completed.returncode
        return returncode
    finally:
        if container_started:
            removed = _run(
                ["docker", "rm", "--force", temporary_container],
                check=False,
                capture_output=True,
            )
            metadata["temporary_container_remove_returncode"] = removed.returncode
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        _append_metadata_to_bundle(output, metadata_path)


if __name__ == "__main__":
    raise SystemExit(main())
