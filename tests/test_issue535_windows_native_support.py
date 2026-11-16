"""Issue #535: Windows-native support keeps the Linux/Docker contracts.

Platform-neutral contracts run everywhere; Windows-only behaviour (Job Objects,
msvcrt locks, drive paths, GlobalMemoryStatusEx) is skipped elsewhere and must be
run on Windows as part of the portable-build validation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

IS_WINDOWS = os.name == "nt"
windows_only = pytest.mark.skipif(not IS_WINDOWS, reason="Windows-native behaviour")
posix_only = pytest.mark.skipif(IS_WINDOWS, reason="POSIX behaviour")


# --- input references and binary reads -----------------------------------------


def test_drive_path_detection_is_windows_only() -> None:
    from src.pipeline.engine_input_safety import _is_windows_drive_path

    assert _is_windows_drive_path(r"C:\scores\a.pdf", os_name="nt")
    assert _is_windows_drive_path("c:/scores/a.pdf", os_name="nt")
    assert not _is_windows_drive_path("C:relative.pdf", os_name="nt")
    assert not _is_windows_drive_path("file:///C:/a.pdf", os_name="nt")
    assert not _is_windows_drive_path("http://example.invalid/a.pdf", os_name="nt")
    assert not _is_windows_drive_path(r"C:\scores\a.pdf", os_name="posix")


def _rejected(reference: str) -> bool:
    from src.pipeline.engine_input_safety import InputSafetyError, validate_local_input_reference

    try:
        validate_local_input_reference(reference)
    except InputSafetyError:
        return True
    return False


@windows_only
def test_windows_accepts_drive_paths_and_rejects_unc_device_and_urls() -> None:
    assert not _rejected(r"C:\scores\楽譜.pdf")
    assert not _rejected("score.pdf")
    for reference in (
        r"\\server\share\a.pdf",
        r"\\?\C:\a.pdf",
        "//server/share/a.pdf",
        "file:///C:/a.pdf",
        "https://example.invalid/a.pdf",
        r"C:\scores\..\secret.pdf",
    ):
        assert _rejected(reference), reference


@posix_only
def test_posix_keeps_rejecting_drive_like_references() -> None:
    assert _rejected(r"C:\scores\a.pdf")
    assert _rejected("file:///tmp/a.pdf")
    assert not _rejected("score.pdf")


def test_bounded_read_is_binary(tmp_path: Path) -> None:
    from src.pipeline.engine_input_safety import _read_bounded_file

    payload = b"%PDF-1.4\r\n\x1a\x00binary\r\ntail\n"
    path = tmp_path / "input.pdf"
    path.write_bytes(payload)

    data, size, _digest = _read_bounded_file(path, max_bytes=1024, allow_symlinks=False)

    assert bytes(data) == payload
    assert size == len(payload)


def test_perf_trace_cpu_seconds_without_resource_module() -> None:
    from src.pipeline import perf_trace

    assert isinstance(perf_trace._cpu_seconds(), float)


# --- owned process trees ---------------------------------------------------------

_SPAWN_GRANDCHILD = r"""
import subprocess, sys, time
pid_file = sys.argv[1]
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
with open(pid_file, "w") as handle:
    handle.write(str(grandchild.pid))
if sys.argv[2] == "exit":
    sys.exit(0)
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    if IS_WINDOWS:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(
            0x1000 | 0x00100000, False, pid
        )  # QUERY_LIMITED | SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie still answers kill(0); treat it as dead
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True


def _wait_for(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _grandchild_pid(pid_file: Path) -> int:
    assert _wait_for(lambda: pid_file.is_file() and pid_file.read_text().strip() != "")
    return int(pid_file.read_text())


@pytest.mark.parametrize("mode", ["exit", "stay"])
def test_owned_tree_kills_grandchildren(tmp_path: Path, mode: str) -> None:
    from src.common.process_tree import OwnedProcessTree

    pid_file = tmp_path / "grandchild.pid"
    with OwnedProcessTree([sys.executable, "-c", _SPAWN_GRANDCHILD, str(pid_file), mode]) as tree:
        grandchild = _grandchild_pid(pid_file)
        if mode == "exit":  # the parent exits first; the grandchild is re-parented
            assert _wait_for(lambda: tree.poll() is not None)
        assert _alive(grandchild)
    assert _wait_for(lambda: not _alive(grandchild))


def test_source_jobs_timeout_and_cancel_kill_the_tree(tmp_path: Path) -> None:
    from src.pipeline.detection.source_concurrency import SourceJobs

    pid_file = tmp_path / "grandchild.pid"
    jobs = SourceJobs(3)
    with pytest.raises(TimeoutError):
        jobs.run([sys.executable, "-c", _SPAWN_GRANDCHILD, str(pid_file), "stay"])
    grandchild = _grandchild_pid(pid_file)
    assert _wait_for(lambda: not _alive(grandchild))

    cancelled = SourceJobs(30)
    cancelled.cancelled.set()
    from src.pipeline.detection.source_concurrency import SourceCancelled

    with pytest.raises(SourceCancelled):
        cancelled.run([sys.executable, "-c", "pass"])


def test_source_jobs_reaps_tree_after_leader_exit(tmp_path: Path) -> None:
    from src.pipeline.detection.source_concurrency import SourceJobs

    pid_file = tmp_path / "grandchild.pid"
    result = SourceJobs(30).run([sys.executable, "-c", _SPAWN_GRANDCHILD, str(pid_file), "exit"])

    assert result.returncode == 0
    grandchild = _grandchild_pid(pid_file)
    assert _wait_for(lambda: not _alive(grandchild))


@windows_only
def test_owner_exit_kills_its_tree(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    owner = (
        "import sys, time\n"
        "from src.common.process_tree import OwnedProcessTree\n"
        f"tree = OwnedProcessTree([sys.executable, '-c', {_SPAWN_GRANDCHILD!r}, sys.argv[1], 'stay'])\n"
        "time.sleep(120)\n"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    process = subprocess.Popen([sys.executable, "-c", owner, str(pid_file)], env=env)
    try:
        grandchild = _grandchild_pid(pid_file)
        assert _alive(grandchild)
        process.kill()  # the owner dies without cleanup; its job handle closes
        process.wait()
        assert _wait_for(lambda: not _alive(grandchild))
    finally:
        if process.poll() is None:
            process.kill()


@windows_only
def test_windows_available_ram_is_reported() -> None:
    from src.pipeline.detection.source_concurrency import _windows_available_ram_bytes

    assert _windows_available_ram_bytes() > 0


# --- lock files ------------------------------------------------------------------


def test_lock_is_exclusive_until_closed(tmp_path: Path) -> None:
    from src.common.file_lock import lock_exclusive_nonblocking, open_lock_file

    path = tmp_path / ".apply.lock"
    with os.fdopen(open_lock_file(path), "r+") as first:
        lock_exclusive_nonblocking(first)
        with os.fdopen(open_lock_file(path), "r+") as second:
            with pytest.raises(BlockingIOError):
                lock_exclusive_nonblocking(second)
    with os.fdopen(open_lock_file(path, create=False), "r+") as again:
        lock_exclusive_nonblocking(again)


def test_lock_is_exclusive_across_processes(tmp_path: Path) -> None:
    from src.common.file_lock import lock_exclusive_nonblocking, open_lock_file

    path = tmp_path / ".transaction.lock"
    probe = (
        "import os, sys\n"
        "from src.common.file_lock import lock_exclusive_nonblocking, open_lock_file\n"
        "fd = open_lock_file(sys.argv[1])\n"
        "try:\n"
        "    lock_exclusive_nonblocking(fd)\n"
        "except BlockingIOError:\n"
        "    sys.exit(3)\n"
        "sys.exit(0)\n"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    with os.fdopen(open_lock_file(path), "r+") as held:
        lock_exclusive_nonblocking(held)
        busy = subprocess.run([sys.executable, "-c", probe, str(path)], env=env, check=False)
    free = subprocess.run([sys.executable, "-c", probe, str(path)], env=env, check=False)

    assert busy.returncode == 3
    assert free.returncode == 0


def test_lock_file_refuses_symlinks(tmp_path: Path) -> None:
    from src.common.file_lock import open_lock_file

    target = tmp_path / "target"
    target.write_text("")
    link = tmp_path / "link.lock"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted for this user")
    with pytest.raises(OSError):
        open_lock_file(link)
    with pytest.raises(FileNotFoundError):
        open_lock_file(tmp_path / "missing.lock", create=False)


# --- local review relocation -----------------------------------------------------


def _package(tmp_path: Path, old_root: str, *, sep: str, extra=None) -> Path:
    package = tmp_path / "job-one"
    review = package / "review"
    review.mkdir(parents=True)
    (review / "manual_correction_input.json").write_text(
        json.dumps({"source_job_id": "job-one", "pages": []})
    )
    retained_run = package / ".engine-retained" / "runs" / "job-one"
    (retained_run / "inputs" / "images").mkdir(parents=True)
    (retained_run / "inputs" / "images" / "page.png").write_bytes(b"png")
    run_dir = sep.join([old_root, "runs", "job-one"])
    manifest = {
        "run_dir": run_dir,
        "pages": [{"image": sep.join([run_dir, "inputs", "images", "page.png"])}],
        "config": {"threshold": 0.5},
    }
    manifest.update(extra or {})
    (retained_run / "manifest.json").write_text(json.dumps(manifest))
    return package


def _local_manifest(package: Path) -> dict:
    path = package / ".engine-retained" / "runs" / "job-one" / "local_manifest.json"
    return json.loads(path.read_text())


@windows_only
def test_relocation_handles_windows_engine_paths(tmp_path: Path) -> None:
    from docker.distribution_job import prepare_local_review

    package = _package(tmp_path, r"C:\out\job-one\.engine-work", sep="\\")
    prepare_local_review(package)
    local = _local_manifest(package)

    assert Path(local["pages"][0]["image"]).is_file()
    assert local["local_distribution_relocation"] == {
        "relocated_path_count": 2,
        "missing_relocated_path_count": 0,
    }


def test_relocation_counts_posix_engine_paths(tmp_path: Path) -> None:
    from docker.distribution_job import prepare_local_review

    package = _package(tmp_path, "/results/job-one/.engine-work", sep="/")
    prepare_local_review(package)
    local = _local_manifest(package)

    assert Path(local["pages"][0]["image"]).is_relative_to(package / ".engine-retained")
    assert local["local_distribution_relocation"]["relocated_path_count"] == 2


def test_relocation_rejects_leftover_references(tmp_path: Path) -> None:
    from docker.distribution_job import prepare_local_review

    old_root = "/results/job-one/.engine-work"
    package = _package(
        tmp_path, old_root, sep="/", extra={"command": f"python run.py --root {old_root}/runs"}
    )
    with pytest.raises(ValueError, match="left 1 references"):
        prepare_local_review(package)


def test_windows_job_ids_are_short_and_safe() -> None:
    from docker.distribution_job import _windows_job_id

    ids = {_windows_job_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(len(value) == 16 and value.startswith("job-") for value in ids)


# --- runtime location, fonts and CUDA fail-closed --------------------------------


def _write_overlay(path: Path, profile: str, runtime: dict) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.homr_profile_runtime.v1",
                "profile": profile,
                "runtime": runtime,
            }
        )
    )
    return path


def test_profile_runtime_overlay_replaces_only_runtime(tmp_path: Path, monkeypatch) -> None:
    from src.pipeline.detection.maintained_profile import PROFILE_PATH
    from src.pipeline.detection.profile_contract import load_profile_manifest

    tracked = load_profile_manifest("maintained_original", PROFILE_PATH)
    runtime = {key: str(tmp_path / key) for key in tracked["runtime"]}
    overlay = _write_overlay(tmp_path / "runtime.json", "maintained_original", runtime)
    monkeypatch.setenv("PDFSCORE_HOMR_PROFILE_RUNTIME", str(overlay))

    loaded = load_profile_manifest("maintained_original", PROFILE_PATH)

    assert loaded["runtime"] == runtime
    assert loaded["homr"] == tracked["homr"]
    assert loaded["pdfscore_evaluator"] == tracked["pdfscore_evaluator"]
    assert loaded["runtime_overlay"] == str(overlay.resolve())


def test_profile_runtime_overlay_is_validated(tmp_path: Path, monkeypatch) -> None:
    from src.pipeline.detection.maintained_profile import PROFILE_PATH
    from src.pipeline.detection.profile_contract import load_profile_manifest

    overlay = _write_overlay(tmp_path / "runtime.json", "other_profile", {"python": "x"})
    monkeypatch.setenv("PDFSCORE_HOMR_PROFILE_RUNTIME", str(overlay))
    with pytest.raises(ValueError, match="Invalid HOMR profile runtime overlay"):
        load_profile_manifest("maintained_original", PROFILE_PATH)

    partial = _write_overlay(tmp_path / "partial.json", "maintained_original", {"python": "x"})
    monkeypatch.setenv("PDFSCORE_HOMR_PROFILE_RUNTIME", str(partial))
    with pytest.raises(ValueError, match="runtime lacks"):
        load_profile_manifest("maintained_original", PROFILE_PATH)


def test_configured_label_font_must_load(tmp_path: Path, monkeypatch) -> None:
    from src.pipeline.review import final_output

    monkeypatch.setenv("PDFSCORE_LABEL_FONT", str(tmp_path / "missing.ttf"))
    with pytest.raises(RuntimeError, match="Configured label font"):
        final_output._load_label_font(20)


@windows_only
def test_windows_without_label_font_fails(monkeypatch) -> None:
    from src.pipeline.review import final_output

    monkeypatch.delenv("PDFSCORE_LABEL_FONT", raising=False)
    monkeypatch.setattr(final_output, "_LABEL_FONT_CANDIDATES", ("missing-font.ttf",))
    with pytest.raises(RuntimeError, match="No label font"):
        final_output._load_label_font(20)


class _FakeSession:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return list(self._providers)


def test_cuda_session_records_fail_closed_on_cpu_fallback() -> None:
    from src.pipeline.detection.ort_session_audit import (
        install_session_recorder,
        validate_cuda_sessions,
    )

    class FakeOrt:
        @staticmethod
        def InferenceSession(path, providers=None):  # noqa: N802 - ORT API name
            return _FakeSession(["CPUExecutionProvider"])

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    records, restore = install_session_recorder(FakeOrt)
    FakeOrt.InferenceSession("segnet.onnx", providers=["CUDAExecutionProvider"])
    restore()

    assert records[0]["active_providers"] == ["CPUExecutionProvider"]
    with pytest.raises(RuntimeError, match="CUDA"):
        validate_cuda_sessions(records, use_gpu_inference=True, ort=FakeOrt)
    validate_cuda_sessions(records, use_gpu_inference=False, ort=FakeOrt)


def test_rapidocr_cpu_fallback_is_fatal_only_in_strict_mode(monkeypatch, caplog) -> None:
    from src.measure_numbering import rapidocr_provider

    class FakeRapidOCR:
        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(rapidocr_provider, "RapidOCR", FakeRapidOCR)
    monkeypatch.setattr(
        rapidocr_provider,
        "collect_rapidocr_providers",
        lambda _engine: {"det": ["CPUExecutionProvider"]},
    )
    monkeypatch.setattr(rapidocr_provider, "onnxruntime_has_cuda_provider", lambda: True)

    monkeypatch.delenv("PDFSCORE_REQUIRE_CUDA_ORT", raising=False)
    assert isinstance(rapidocr_provider.create_mmr_rapidocr("auto"), FakeRapidOCR)

    monkeypatch.setenv("PDFSCORE_REQUIRE_CUDA_ORT", "1")
    with pytest.raises(RuntimeError, match="not on CUDAExecutionProvider"):
        rapidocr_provider.create_mmr_rapidocr("auto")
    monkeypatch.setattr(rapidocr_provider, "onnxruntime_has_cuda_provider", lambda: False)
    with pytest.raises(RuntimeError, match="not on CUDAExecutionProvider"):
        rapidocr_provider.create_mmr_rapidocr("auto")


@windows_only
def test_sr_compiler_cache_is_explicitly_unsupported_on_windows(tmp_path: Path) -> None:
    from src.pipeline.detection.sr_compiler_cache import lease

    with pytest.raises(RuntimeError, match="not supported on Windows"):
        with lease(tmp_path, {}):
            pass


@windows_only
def test_windows_never_delegates_to_a_docker_container() -> None:
    from src.pipeline.core.python_env import get_docker_exec_prefix, get_pipeline_python

    assert get_docker_exec_prefix() == []
    assert get_pipeline_python("homr")[0] in {sys.executable, os.environ.get("PIPELINE_PYTHON")}
