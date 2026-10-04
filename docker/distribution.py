#!/usr/bin/env python3
"""Operate the Linux/NVIDIA Docker distribution without development tooling."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from docker.runtime_contract import runtime_fingerprint, source_fingerprint
from src.common.model_artifacts import resolve_model_artifact


def capture(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def source_identity() -> dict:
    provenance = ROOT / "DISTRIBUTION_PROVENANCE.json"
    if provenance.is_file():
        return json.loads(provenance.read_text(encoding="utf-8"))
    return {
        "source_commit": capture(["git", "rev-parse", "HEAD"]),
        "source_branch": capture(["git", "branch", "--show-current"]) or "detached",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="pdfscore_pipeline_gpu")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    commands.add_parser("preflight")
    run = commands.add_parser("run")
    run.add_argument("pdf", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--pages", type=int, nargs="+")
    review = commands.add_parser("review")
    review.add_argument("--output", type=Path, required=True, help="Same output root as run")
    review.add_argument("--handoff", type=Path, required=True)
    review.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    identity = source_identity()
    commit = identity["source_commit"]
    branch = identity["source_branch"]
    if args.command == "build":
        return subprocess.call(
            [
                "docker",
                "build",
                "--build-arg",
                f"PDFSCORE_SOURCE_COMMIT={commit}",
                "--build-arg",
                f"PDFSCORE_SOURCE_BRANCH={branch}",
                "--build-arg",
                f"PDFSCORE_SOURCE_FINGERPRINT={source_fingerprint(ROOT)}",
                "-t",
                args.image,
                ".",
            ],
            cwd=ROOT,
        )
    info = json.loads(capture(["docker", "image", "inspect", args.image]))[0]
    labels = info["Config"].get("Labels") or {}
    if labels.get("pdfscore.runtime.asset_contract") != "v1" or not labels.get(
        "pdfscore.runtime.source_fingerprint"
    ):
        raise ValueError(
            "Image lacks production asset/source provenance; build this distribution first"
        )
    image_id = info["Id"]
    embedded = capture(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/opt/venv_pipeline/bin/python",
            image_id,
            "/opt/pdfscore-runtime/runtime_contract.py",
            "runtime-fingerprint",
            "/workspace",
        ]
    )
    fingerprint = runtime_fingerprint(ROOT)
    if embedded != fingerprint:
        raise ValueError(
            "Image runtime contract differs from distribution; build this distribution first"
        )
    manifest = ROOT / "models/omr_dln/manifest.json"
    omr = resolve_model_artifact(manifest, project_root=ROOT).resolve()
    runtime_path = json.loads(manifest.read_text())["runtime_path"]
    common = [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--network",
        "none",
        "-v",
        f"{ROOT}:/workspace:ro",
        "-v",
        f"{omr}:{runtime_path}:ro",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        "-e",
        f"OMR_DLN_MODEL_PATH={runtime_path}",
        "-e",
        f"PDFSCORE_HOST_SOURCE_COMMIT={commit}",
        "-e",
        f"PDFSCORE_HOST_SOURCE_BRANCH={branch}",
        "-e",
        f"PDFSCORE_HOST_SOURCE_ROOT={ROOT}",
        "-e",
        f"PDFSCORE_DOCKER_IMAGE_ID={image_id}",
        "-e",
        f"PDFSCORE_DOCKER_IMAGE_REF={args.image}",
    ]
    status = subprocess.call(
        common
        + [
            image_id,
            "/opt/venv_pipeline/bin/python",
            "docker/runtime_contract.py",
            "preflight",
            "--config",
            "configs/dense_full_pipeline.yaml",
            "--expected-fingerprint-value",
            fingerprint,
        ],
        cwd=ROOT,
    )
    if status or args.command == "preflight":
        return status
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    common += ["-v", f"{output}:/results"]
    if args.command == "run":
        pdf = args.pdf.resolve(strict=True)
        common += ["-v", f"{pdf.parent}:/input:ro"]
        command = [
            "/opt/venv_pipeline/bin/python",
            "-m",
            "docker.distribution_job",
            f"/input/{pdf.name}",
            "--output",
            "/results",
        ]
        if args.pages:
            command += ["--pages", *map(str, args.pages)]
    else:
        handoff = args.handoff.resolve(strict=True).relative_to(output)
        # The existing user server binds container loopback. Linux host networking
        # preserves its loopback/same-origin contract without widening that bind.
        common[common.index("none")] = "host"
        command = [
            "/opt/venv_pipeline/bin/python",
            "-m",
            "tools.review_correction.server",
            "--handoff",
            f"/results/{handoff.as_posix()}",
            "--port",
            str(args.port),
        ]
    print(
        json.dumps(
            {"source": identity, "image_id": image_id, "runtime_fingerprint": fingerprint}, indent=2
        ),
        flush=True,
    )
    return subprocess.call(common + [image_id, *command], cwd=ROOT)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
