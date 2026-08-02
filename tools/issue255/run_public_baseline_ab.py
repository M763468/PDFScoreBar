#!/usr/bin/env python3
"""Run the Issue #255 two-page current/public-baseline HOMR A/B."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BRANCH = "fix/issue255-fresh-detector-production-recovery"
ISSUE245_TOOLING_COMMIT = "3b9f5c4c74f284dab0e09816e1983fd81109adbc"
PDFSCORE_PROFILE_COMMIT = "bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7"
HOMR_PROFILE_COMMIT = "864e2882f7a41afcf8f16654728a473ae56826d6"
PUBLIC_IMAGE = f"pdfscorebar-issue255-public-baseline:{HOMR_PROFILE_COMMIT[:12]}"
DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue255_public_baseline_ab"
PROFILE_MANIFEST = ROOT / "tools/issue255/public_baseline_homr_profile.json"
PUBLIC_DOCKERFILE = ROOT / "tools/issue255/Dockerfile.public_baseline_homr"
VARIANT_RUNNER = ROOT / "tools/issue255/run_public_baseline_ab_variant.py"
PAGES = (
    (
        "prokofiev",
        "Va_Prokofiev_Symphony1",
        "page_004",
        ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
    ),
    (
        "shostakovich",
        "Shostakovich-Sym5-Va",
        "page_014",
        ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png",
    ),
)


def _run(
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    log: Path | None = None,
    input_text: str | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-3000:]
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    if not capture and log is None:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    return result


def _git(*args: str) -> str:
    return _run(("git", *args), capture=True).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_commit(commit: str) -> None:
    probe = subprocess.run(
        ("git", "cat-file", "-e", f"{commit}^{{commit}}"),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        _run(("git", "fetch", "--no-tags", "origin", commit))
    _run(("git", "cat-file", "-e", f"{commit}^{{commit}}"), capture=True)


def _write_git_file(commit: str, source: str, destination: Path) -> None:
    payload = _run(("git", "show", f"{commit}:{source}"), capture=True).stdout
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def _extract_snapshot(commit: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as stream:
        _run(("git", "archive", "--format=tar", f"--output={stream.name}", commit), capture=True)
        _run(("tar", "-xf", stream.name, "-C", str(destination)), capture=True)


def _require_executable(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(f"Required command not found: {command}")


def _container_path(path: Path) -> str:
    return "/workspace/" + str(path.resolve().relative_to(ROOT)).replace(os.sep, "/")


def _find_omr_model(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate
    env_value = os.environ.get("OMR_DLN_MODEL_PATH")
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if candidate.is_file():
            return candidate
    repository_default = ROOT / "external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
    if repository_default.is_file():
        return repository_default.resolve()
    matches = list(Path.home().rglob("YOLOv8m_Measures.pt"))[:11]
    if len(matches) == 1:
        return matches[0].resolve()
    if len(matches) > 1:
        choices = "\n".join(f"  {path}" for path in matches[:10])
        raise RuntimeError(f"Multiple YOLOv8m_Measures.pt files found; use --omr-model:\n{choices}")
    raise FileNotFoundError("Official YOLOv8m_Measures.pt was not found")


def _validate_profile() -> dict[str, Any]:
    payload = json.loads(PROFILE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid public baseline HOMR profile")
    if payload.get("historical_candidate_artifact_runtime_input") is not False:
        raise ValueError("Profile permits historical candidate runtime input")
    homr = payload.get("homr")
    if not isinstance(homr, Mapping) or homr.get("commit") != HOMR_PROFILE_COMMIT:
        raise ValueError("Public baseline HOMR commit mismatch")
    result = payload.get("verified_full68_result")
    if not isinstance(result, Mapping) or result.get("pages_semantic_equal") != 68:
        raise ValueError("Public baseline full-68 verification is missing")
    return dict(payload)


def _prepare_public_image(
    *, container: str, rebuild: bool, output_root: Path
) -> str:
    base_image = _run(
        ("docker", "inspect", "--format", "{{.Config.Image}}", container), capture=True
    ).stdout.strip()
    if not base_image:
        raise RuntimeError("Could not resolve production container image")
    exists = (
        subprocess.run(
            ("docker", "image", "inspect", PUBLIC_IMAGE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    if rebuild or not exists:
        command = [
            "docker",
            "build",
            "--file",
            str(PUBLIC_DOCKERFILE),
            "--build-arg",
            f"BASE_IMAGE={base_image}",
            "--build-arg",
            f"HOMR_COMMIT={HOMR_PROFILE_COMMIT}",
            "--tag",
            PUBLIC_IMAGE,
        ]
        if rebuild:
            command.append("--no-cache")
        command.append(str(ROOT))
        _run(command, log=output_root / "profile/docker_build.log")
    else:
        (output_root / "profile/docker_build.log").write_text(
            f"Reused existing image {PUBLIC_IMAGE}\n", encoding="utf-8"
        )
    return base_image


def _copy_model_into_container(container: str, model: Path) -> tuple[str, str | None]:
    try:
        relative = model.relative_to(ROOT)
    except ValueError:
        digest = _sha256(model)
        directory = f"/tmp/issue255_ab_omr_{digest}"
        target = f"{directory}/YOLOv8m_Measures.pt"
        _run(("docker", "exec", "--user", "0:0", container, "mkdir", "-p", directory))
        _run(("docker", "cp", str(model), f"{container}:{target}"))
        _run(("docker", "exec", "--user", "0:0", container, "chmod", "0444", target))
        return target, directory
    target = "/workspace/" + str(relative).replace(os.sep, "/")
    _run(("docker", "exec", container, "test", "-f", target), capture=True)
    return target, None


def _write_handoff(
    *, image: Path, detection: Path, provenance: Path, output: Path
) -> None:
    payload = {
        "schema_version": "issue255.public_baseline_handoff.v1",
        "status": "completed",
        "freshly_generated": True,
        "historical_artifact_used_as_runtime_input": False,
        "source_image_path": str(image.resolve()),
        "source_image_sha256": _sha256(image),
        "detection_path": _container_path(detection),
        "detection_sha256": _sha256(detection),
        "provenance_path": _container_path(provenance),
        "provenance_sha256": _sha256(provenance),
        "homr_commit": HOMR_PROFILE_COMMIT,
        "pdfscore_evaluator_commit": PDFSCORE_PROFILE_COMMIT,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_batches(*, root: Path, run_tag: str, commit: str) -> tuple[Path, Path]:
    outputs = []
    for variant, prefix in (
        ("control", "issue255_ab_control_"),
        ("public_baseline", "issue255_ab_public_"),
    ):
        runs = []
        for label, score, page, _image in PAGES:
            run_id = f"{prefix}{label}_{page}_{run_tag}"
            contract_path = (
                root
                / "runs"
                / run_id
                / "issue255_public_baseline_ab_run_contract.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            runs.append(
                {
                    "label": label,
                    "score": score,
                    "page": page,
                    "run_id": run_id,
                    "runner_exit_code": 0,
                    "detail": str(contract_path),
                    "contract_path": str(contract_path.resolve()),
                    "contract": contract,
                    "errors": [],
                }
            )
        payload = {
            "schema_version": "issue255.public_baseline_ab_batch.v1",
            "status": "completed",
            "variant": variant,
            "expected_commit": commit,
            "expected_branch": EXPECTED_BRANCH,
            "low_paper_rescue_enabled": False,
            "runs": runs,
            "errors": [],
        }
        path = root / f"issue255_{variant}_batch_{run_tag}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        outputs.append(path)
    return outputs[0], outputs[1]


def run_ab(args: argparse.Namespace) -> tuple[Path, Path]:
    for command in ("docker", "git", "tar"):
        _require_executable(command)
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError(f"Expected branch {EXPECTED_BRANCH}")
    if _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError(
            "Tracked working tree must be clean before authoritative A/B execution"
        )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_tag):
        raise ValueError("--run-tag contains unsupported characters")
    for path in (PROFILE_MANIFEST, PUBLIC_DOCKERFILE, VARIANT_RUNNER):
        if not path.is_file():
            raise FileNotFoundError(path)
    _validate_profile()

    output_base = args.output_root.expanduser().resolve()
    try:
        output_base.relative_to(ROOT)
    except ValueError as error:
        raise ValueError("--output-root must be inside the repository") from error
    ab_root = output_base / args.run_tag
    if ab_root.exists():
        raise FileExistsError(ab_root)
    (ab_root / "tooling").mkdir(parents=True)
    (ab_root / "profile").mkdir(parents=True)
    (ab_root / "runs").mkdir(parents=True)

    _ensure_commit(ISSUE245_TOOLING_COMMIT)
    _ensure_commit(PDFSCORE_PROFILE_COMMIT)
    compat = ab_root / "tooling/run_homr_evaluator_compat.py"
    _write_git_file(
        ISSUE245_TOOLING_COMMIT,
        "tools/issue245/run_homr_evaluator_compat.py",
        compat,
    )
    snapshot = ab_root / "profile/pdfscore_source_snapshot"
    _extract_snapshot(PDFSCORE_PROFILE_COMMIT, snapshot)

    running = _run(("docker", "ps", "--format", "{{.Names}}"), capture=True).stdout.splitlines()
    if args.container not in running:
        raise RuntimeError(f"Production container is not running: {args.container}")
    _run(
        ("docker", "exec", args.container, "test", "-x", args.container_python),
        capture=True,
    )
    head = _git("rev-parse", "HEAD")
    container_head = _run(
        (
            "docker",
            "exec",
            "-w",
            "/workspace",
            "-e",
            "GIT_CONFIG_COUNT=1",
            "-e",
            "GIT_CONFIG_KEY_0=safe.directory",
            "-e",
            "GIT_CONFIG_VALUE_0=/workspace",
            args.container,
            "git",
            "rev-parse",
            "HEAD",
        ),
        capture=True,
    ).stdout.strip()
    if container_head != head:
        raise RuntimeError(
            f"Container /workspace HEAD mismatch: host={head} container={container_head}"
        )

    _prepare_public_image(
        container=args.container,
        rebuild=args.rebuild_public_image,
        output_root=ab_root,
    )
    model = _find_omr_model(args.omr_model)
    container_model, copied_directory = _copy_model_into_container(args.container, model)
    uid_gid = f"{os.getuid()}:{os.getgid()}"

    try:
        bootstrap = ab_root / "profile/current_homr_bootstrap.json"
        _run(
            (
                "docker",
                "exec",
                "--user",
                "0:0",
                "-w",
                "/workspace",
                "-e",
                "PYTHONPATH=/workspace",
                args.container,
                args.container_python,
                "tools/issue255/bootstrap_homr_models.py",
                "--output",
                _container_path(bootstrap),
            ),
            log=ab_root / "profile/current_homr_bootstrap.log",
        )
        _run(
            (
                "docker",
                "exec",
                "--user",
                "0:0",
                args.container,
                "chown",
                uid_gid,
                _container_path(bootstrap),
            )
        )

        config = yaml.safe_load(
            (ROOT / "configs/dense_full_pipeline.yaml").read_text(encoding="utf-8")
        )
        hybrid_root = (ROOT / config["detection"]["hybrid_output_root"]).resolve()
        hybrid_root.relative_to(ROOT)
        runs_root_container = _container_path(ab_root / "runs")

        for label, score, page, image in PAGES:
            if not image.is_file():
                raise FileNotFoundError(image)
            control_run = f"issue255_ab_control_{label}_{page}_{args.run_tag}"
            public_run = f"issue255_ab_public_{label}_{page}_{args.run_tag}"
            common_exec = (
                "docker",
                "exec",
                "--user",
                uid_gid,
                "-w",
                "/workspace",
                "-e",
                "PYTHONPATH=/workspace",
                "-e",
                "HOME=/tmp",
                "-e",
                "YOLO_CONFIG_DIR=/tmp/issue255_ab_ultralytics",
                "-e",
                f"OMR_DLN_MODEL_PATH={container_model}",
                args.container,
                args.container_python,
                "tools/issue255/run_public_baseline_ab_variant.py",
            )
            _run(
                (
                    *common_exec,
                    "--variant",
                    "control",
                    "--image",
                    _container_path(image),
                    "--score",
                    score,
                    "--page",
                    page,
                    "--run-id",
                    control_run,
                    "--output-root",
                    runs_root_container,
                ),
                log=ab_root / f"{control_run}.log",
            )

            baseline_host = hybrid_root / public_run / "baseline"
            baseline_host.mkdir(parents=True)
            baseline_container = _container_path(baseline_host)
            public_env = (
                "PYTHONPATH=/opt/issue255_public_homr:"
                "/historical:/historical/src:/workspace"
            )
            _run(
                (
                    "docker",
                    "run",
                    "--rm",
                    "--gpus",
                    "all",
                    "-v",
                    f"{ROOT}:/workspace",
                    "-v",
                    f"{snapshot}:/historical:ro",
                    "-w",
                    "/workspace",
                    "-e",
                    "HOME=/tmp",
                    "-e",
                    public_env,
                    PUBLIC_IMAGE,
                    "/opt/venv_pipeline/bin/python",
                    _container_path(compat),
                    "--images",
                    _container_path(image),
                    "--output-root",
                    baseline_container,
                    "--force-run-id",
                    "batch",
                    "--enable-segnet-cache",
                ),
                log=ab_root / f"{public_run}_public_baseline.log",
            )
            detection = baseline_host / "batch" / page / f"{page}_detections.json"
            if not detection.is_file():
                raise FileNotFoundError(detection)

            provenance = ab_root / "profile" / f"{public_run}_provenance.json"
            provenance_code = """
import hashlib, json, sys
from pathlib import Path
import cv2, numpy, onnxruntime
root = Path('/opt/issue255_public_homr')
models = [
 root / 'homr/segmentation/segnet_155-1240eedca553155b3c75fc9c7f643465383430a0.onnx',
 root / 'homr/transformer/decoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx',
 root / 'homr/transformer/encoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx',
]
def digest(path):
 h = hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
 return h.hexdigest()
payload = {
 'schema_version': 'issue255.public_baseline_profile.v1',
 'homr_commit': Path('/opt/issue255_public_homr_commit.txt').read_text().strip(),
 'numpy': numpy.__version__, 'opencv': cv2.__version__,
 'onnxruntime': onnxruntime.__version__,
 'available_providers': onnxruntime.get_available_providers(),
 'models': [{'path': str(path), 'sha256': digest(path)} for path in models],
 'historical_artifact_used_as_runtime_input': False,
}
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + '\\n', encoding='utf-8')
"""
            _run(
                (
                    "docker",
                    "run",
                    "--rm",
                    "--gpus",
                    "all",
                    "-v",
                    f"{ROOT}:/workspace",
                    "-w",
                    "/workspace",
                    "-e",
                    "HOME=/tmp",
                    "-e",
                    "PYTHONPATH=/opt/issue255_public_homr:/workspace",
                    PUBLIC_IMAGE,
                    "/opt/venv_pipeline/bin/python",
                    "-c",
                    provenance_code,
                    _container_path(provenance),
                ),
                log=ab_root / f"{public_run}_provenance.log",
            )
            _run(
                (
                    "docker",
                    "exec",
                    "--user",
                    "0:0",
                    args.container,
                    "chown",
                    "-R",
                    uid_gid,
                    baseline_container,
                    _container_path(provenance),
                )
            )
            handoff = ab_root / "profile" / f"{public_run}_handoff.json"
            _write_handoff(
                image=image,
                detection=detection,
                provenance=provenance,
                output=handoff,
            )

            _run(
                (
                    *common_exec,
                    "--variant",
                    "public_baseline",
                    "--image",
                    _container_path(image),
                    "--score",
                    score,
                    "--page",
                    page,
                    "--run-id",
                    public_run,
                    "--output-root",
                    runs_root_container,
                    "--baseline-handoff",
                    _container_path(handoff),
                ),
                log=ab_root / f"{public_run}.log",
            )
    finally:
        if copied_directory:
            subprocess.run(
                (
                    "docker",
                    "exec",
                    "--user",
                    "0:0",
                    args.container,
                    "rm",
                    "-rf",
                    copied_directory,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    return _write_batches(root=ab_root, run_tag=args.run_tag, commit=head)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--container",
        default=os.environ.get("ISSUE255_CONTAINER", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--container-python", default="/opt/venv_pipeline/bin/python")
    parser.add_argument("--omr-model", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--rebuild-public-image", action="store_true")
    args = parser.parse_args()
    try:
        control, public = run_ab(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "completed",
                "control_batch": str(control),
                "public_batch": str(public),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
