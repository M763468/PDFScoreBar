"""Run Issue #284 torch.compile screening in a disposable compiler-enabled image.

The production image/container is not mutated. This host-side wrapper derives a
temporary image from the exact image used by ``pdfscore_pipeline_pytest_dev``, adds
only the build toolchain required by Triton/Inductor, reuses the dev container's
mounts, runs the existing screening as the invoking host UID/GID, then removes the
temporary image.
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
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture_output,
        input=input_text,
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


def _dockerfile(base_image: str) -> str:
    return f"""FROM {base_image}\nUSER root\nRUN apt-get update \\\n && apt-get install -y --no-install-recommends build-essential python3.11-dev \\\n && rm -rf /var/lib/apt/lists/*\n"""


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
    tag = f"pdfscore-issue284-compile-probe:{uid}-{int(time.time())}"

    metadata_path = output / "compiler_probe_environment.json"
    metadata = {
        "schema_version": "issue284.compile_probe_environment.v1",
        "base_container": args.container,
        "base_image": base_image,
        "temporary_image": tag,
        "host_uid": uid,
        "host_gid": gid,
        "candidate_summary": str(candidate_summary),
        "output": str(output),
        "toolchain_packages": ["build-essential", "python3.11-dev"],
    }

    print(f"base_image={base_image}")
    print(f"temporary_image={tag}")
    print("Building disposable compiler-enabled image...")

    build = _run(
        ["docker", "build", "--tag", tag, "-"],
        check=False,
        input_text=_dockerfile(base_image),
    )
    metadata["docker_build_returncode"] = build.returncode
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if build.returncode != 0:
        return build.returncode

    container_output = "/workspace/" + str(output.relative_to(ROOT)).replace(os.sep, "/")
    container_summary = "/workspace/" + str(candidate_summary.relative_to(ROOT)).replace(
        os.sep, "/"
    )

    command = [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--volumes-from",
        args.container,
        "--user",
        f"{uid}:{gid}",
        "--workdir",
        "/workspace",
        "--env",
        "CC=/usr/bin/gcc",
        "--env",
        "CXX=/usr/bin/g++",
        tag,
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

    print("Running screening:")
    print(" ".join(shlex.quote(item) for item in command))
    returncode = 1
    try:
        completed = _run(command, check=False)
        metadata["screening_returncode"] = completed.returncode
        returncode = completed.returncode
    finally:
        remove = _run(["docker", "image", "rm", "--force", tag], check=False)
        metadata["temporary_image_remove_returncode"] = remove.returncode
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        _append_metadata_to_bundle(output, metadata_path)

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
