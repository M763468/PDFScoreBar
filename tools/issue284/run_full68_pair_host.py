"""Run the Issue #284 fresh full68 control/candidate pair from the WSL host."""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

CONTROL_COMMIT = "fefd2a3b437bf45caf20aac517dce994596a4681"
CANONICAL_CONTAINER = "pdfscore_pipeline_pytest_dev"
CANONICAL_IMAGE = "pdfscore_pipeline_gpu"
CONTAINER_ROOT = Path("/workspace")
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
RUNNER_REL = Path("tools/issue284/run_full68_variant.py")
# Keep fresh full68 outputs separate from legacy/interrupted Issue #284 artifacts,
# which may have been created by root-owned container runs.
DEFAULT_OUTPUT_ROOT = Path("logs/issue284_full68_runs")
MIN_S_FREE_GIB = 50.0
POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_TAG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class RestoreTarget:
    branch: str | None
    commit: str


class TerminationRequested(RuntimeError):
    pass


_active_child: subprocess.Popen[str] | None = None


def _signal_handler(signum: int, _frame: object) -> None:
    if _active_child is not None and _active_child.poll() is None:
        _active_child.send_signal(signum)
    raise TerminationRequested(f"received signal {signum}")


def capture(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        command,
        cwd=cwd,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def checked(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def git_commit(root: Path, ref: str) -> str:
    value = capture(["git", "rev-parse", f"{ref}^{{commit}}"], cwd=root)
    if not SHA_RE.fullmatch(value):
        raise RuntimeError(f"Unexpected git commit value for {ref}: {value!r}")
    return value


def require_clean(root: Path) -> None:
    status = capture(["git", "status", "--porcelain"], cwd=root)
    if status:
        raise RuntimeError("Issue #284 full68 pair requires a clean host checkout:\n" + status)


def restore_target(root: Path) -> RestoreTarget:
    branch_result = subprocess.run(
        ["git", "symbolic-ref", "--short", "-q", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    branch = branch_result.stdout.strip() or None
    return RestoreTarget(branch=branch, commit=git_commit(root, "HEAD"))


def restore_checkout(root: Path, target: RestoreTarget) -> None:
    old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
    old_term = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        if target.branch is not None:
            checked(["git", "switch", target.branch"], cwd=root)
        else:
            checked(["git", "switch", "--detach", target.commit], cwd=root)

        actual = git_commit(root, "HEAD")
        if actual != target.commit:
            raise RuntimeError(f"Checkout restoration mismatch: {actual} != {target.commit}")
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)


def checkout_exact(root: Path, commit: str) -> None:
    require_clean(root)
    checked(["git", "switch", "--detach", commit], cwd=root)
    actual = git_commit(root, "HEAD")
    if actual != commit:
        raise RuntimeError(f"Checkout mismatch: {actual} != {commit}")
    require_clean(root)


def parse_windows_free_bytes(output: str) -> int:
    values = re.findall(r"\d+", output)
    if not values:
        raise ValueError(f"Could not parse Windows free bytes: {output!r}")
    return int(values[-1])


def s_free_gib() -> float:
    if not POWERSHELL.is_file():
        raise FileNotFoundError(POWERSHELL)

    output = capture(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-Command",
            "[Console]::Out.Write((Get-Volume -DriveLetter S).SizeRemaining)",
        ]
    )
    return parse_windows_free_bytes(output) / (1024**3)


def require_s_free_space() -> float:
    free = s_free_gib()
    print(f"S: free space = {free:.2f} GiB", flush=True)
    if free < MIN_S_FREE_GIB:
        raise RuntimeError(
            f"S: free space {free:.2f} GiB is below "
            f"{MIN_S_FREE_GIB:.0f} GiB safety floor"
        )
    return free


def docker_container_info() -> tuple[bool, str]:
    output = capture(
        [
            "docker",
            "inspect",
            CANONICAL_CONTAINER,
            "--format",
            "{{.State.Running}}|{{.Config.Image}}",
        ]
    )
    running_text, image = output.split("|", maxsplit=1)
    return running_text == "true", image


def require_workspace_mount(root: Path) -> None:
    output = capture(
        [
            "docker",
            "inspect",
            CANONICAL_CONTAINER,
            "--format",
            '{{range .Mounts}}{{println .Source "|" .Destination}}{{end}}',
        ]
    )
    expected_source = str(root.resolve())
    found = False
    for line in output.splitlines():
        if "|" not in line:
            continue
        source, destination = [part.strip() for part in line.split("|", 1)]
        if source == expected_source and destination == str(CONTAINER_ROOT):
            found = True
            break
    if not found:
        raise RuntimeError(f"Expected Docker bind {expected_source} -> {CONTAINER_ROOT}")


def require_host_uid_write_access(root: Path) -> None:
    probe_rel = DEFAULT_OUTPUT_ROOT / f".issue284_uid_probe_{os.getpid()}"
    (root / probe_rel.parent).mkdir(parents=True, exist_ok=True)
    probe_container = CONTAINER_ROOT / probe_rel
    code = (
        "from pathlib import Path; "
        f"p=Path({str(probe_container)!r}); "
        "p.write_text('ok', encoding='utf-8'); "
        "p.unlink()"
    )
    checked(
        [
            "docker",
            "exec",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            CANONICAL_CONTAINER,
            str(PIPELINE_PYTHON),
            "-c",
            code,
        ]
    )


def require_docker_runtime(root: Path) -> None:
    running, image = docker_container_info()
    if not running:
        raise RuntimeError(f"{CANONICAL_CONTAINER} is not running")
    if image != CANONICAL_IMAGE:
        raise RuntimeError(
            f"{CANONICAL_CONTAINER} uses {image!r}, expected {CANONICAL_IMAGE!r}"
        )

    require_workspace_mount(root)

    checked(
        [
            "docker",
            "exec",
            CANONICAL_CONTAINER,
            "test",
            "-x",
            str(PIPELINE_PYTHON),
        ]
    )
    checked(
        [
            "docker",
            "exec",
            CANONICAL_CONTAINER,
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,memory.used",
            "--format=csv,noheader,nounits",
        ]
    )
    checked(
        [
            "docker",
            "exec",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            CANONICAL_CONTAINER,
            str(PIPELINE_PYTHON),
            "-c",
            (
                "import torch; "
                "assert torch.cuda.is_available(); "
                "print(torch.cuda.get_device_name(0))"
            ),
        ]
    )
    require_host_uid_write_access(root)


def validate_run_tag(value: str) -> str:
    if not RUN_TAG_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "run tag may contain only letters, digits, '.', '_' and '-'"
        )
    return value


def output_paths(root: Path, run_tag: str) -> tuple[Path, Path]:
    base = root / DEFAULT_OUTPUT_ROOT
    return (
        base / f"{run_tag}-control",
        base / f"{run_tag}-candidate",
    )


def require_fresh_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output already contains files: {path}")
    path.mkdir(parents=True, exist_ok=True)


def container_path(root: Path, host_path: Path) -> Path:
    relative = host_path.resolve().relative_to(root.resolve())
    return CONTAINER_ROOT / relative


def stage_candidate_runner(
    root: Path,
    candidate_commit: str,
) -> tuple[Path, str]:
    content = subprocess.check_output(
        [
            "git",
            "show",
            f"{candidate_commit}:{RUNNER_REL.as_posix()}",
        ],
        cwd=root,
    )

    handle = tempfile.NamedTemporaryFile(
        prefix="issue284_full68_runner_",
        suffix=".py",
        delete=False,
    )
    try:
        handle.write(content)
        handle.close()
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise

    host_temp = Path(handle.name)
    container_temp = f"/tmp/issue284_full68_runner_{os.getpid()}.py"
    checked(
        [
            "docker",
            "cp",
            str(host_temp),
            f"{CANONICAL_CONTAINER}:{container_temp}",
        ]
    )
    return host_temp, container_temp


def remove_staged_runner(
    host_temp: Path | None,
    container_temp: str | None,
) -> None:
    if container_temp is not None:
        subprocess.run(
            [
                "docker",
                "exec",
                CANONICAL_CONTAINER,
                "rm",
                "-f",
                container_temp,
            ],
            check=False,
        )
    if host_temp is not None:
        host_temp.unlink(missing_ok=True)


def runner_help(container_runner: str) -> None:
    checked(
        [
            "docker",
            "exec",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            CANONICAL_CONTAINER,
            str(PIPELINE_PYTHON),
            container_runner,
            "--help",
        ]
    )


def run_variant(
    *,
    root: Path,
    commit: str,
    output: Path,
    label: str,
    container_runner: str,
) -> None:
    global _active_child

    require_s_free_space()
    checkout_exact(root, commit)
    require_fresh_output(output)

    command = [
        "docker",
        "exec",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        CANONICAL_CONTAINER,
        str(PIPELINE_PYTHON),
        container_runner,
        "--project-root",
        str(CONTAINER_ROOT),
        "--output",
        str(container_path(root, output)),
        "--label",
        label,
        "--source-commit",
        commit,
        "--host-clean-verified",
    ]

    print(
        f"=== {label}: {commit} -> {output.relative_to(root)} ===",
        flush=True,
    )

    process = subprocess.Popen(command, cwd=root, text=True)
    _active_child = process
    try:
        returncode = process.wait()
    finally:
        _active_child = None

    if returncode != 0:
        raise RuntimeError(
            f"{label} full68 failed with return code {returncode}; "
            f"output retained at {output}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--control-ref",
        default=CONTROL_COMMIT,
    )
    parser.add_argument(
        "--candidate-ref",
        default="HEAD",
    )
    parser.add_argument(
        "--run-tag",
        type=validate_run_tag,
        required=True,
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate runtime and checkout restoration without running full68",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    require_clean(root)

    original = restore_target(root)
    control_commit = git_commit(root, args.control_ref)
    candidate_commit = git_commit(root, args.candidate_ref)

    if control_commit != CONTROL_COMMIT:
        raise RuntimeError(
            f"Control must resolve to {CONTROL_COMMIT}, got {control_commit}"
        )
    if control_commit == candidate_commit:
        raise RuntimeError("Control and candidate resolve to the same commit")

    host_temp: Path | None = None
    container_temp: str | None = None

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        print(f"original = {original}", flush=True)
        print(f"control  = {control_commit}", flush=True)
        print(f"candidate = {candidate_commit}", flush=True)

        require_s_free_space()
        require_docker_runtime(root)

        host_temp, container_temp = stage_candidate_runner(
            root,
            candidate_commit,
        )
        runner_help(container_temp)

        if args.preflight_only:
            print("=== checkout restoration smoke ===", flush=True)
            checkout_exact(root, control_commit)
            checkout_exact(root, candidate_commit)
            print("preflight-only PASS", flush=True)
            return 0

        control_output, candidate_output = output_paths(
            root,
            args.run_tag,
        )

        run_variant(
            root=root,
            commit=control_commit,
            output=control_output,
            label="post285-control",
            container_runner=container_temp,
        )
        run_variant(
            root=root,
            commit=candidate_commit,
            output=candidate_output,
            label="issue284-candidate",
            container_runner=container_temp,
        )

        print("full68 pair completed", flush=True)
        print(f"control_output={control_output}", flush=True)
        print(f"candidate_output={candidate_output}", flush=True)
        return 0
    finally:
        remove_staged_runner(host_temp, container_temp)
        restore_checkout(root, original)
        require_clean(root)
        print(
            f"restored checkout: branch={original.branch} commit={original.commit}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
