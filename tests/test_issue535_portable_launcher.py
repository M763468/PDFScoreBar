"""Issue #535: the portable launcher's job pointers, relocation and job-root lock.

These run on every platform: the launcher logic is plain path/JSON handling, and the
lock is the shared ``src.common.file_lock`` used by ``tools.browser_jobs``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tools.browser_jobs.jobs import exclusive_root, new_job_id
from tools.windows_portable import launcher

JOB = "job-0123456789ab"


@pytest.fixture
def jobs(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "PDFScoreBar" / "jobs"
    (root / JOB).mkdir(parents=True)
    monkeypatch.setattr(launcher, "JOBS", root)
    return root


def _pointer(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_pointer_resolves_by_job_id_after_the_folder_moved(jobs: Path, tmp_path: Path) -> None:
    # A pointer written before the move still names the old absolute folder.
    old = tmp_path / "old-location" / "jobs" / JOB
    pointer = _pointer(tmp_path / f"{JOB}.json", {"job": JOB, "job_folder": str(old)})
    assert launcher.resolve_job(str(pointer)) == (jobs / JOB).resolve()
    assert launcher.resolve_job(JOB) == (jobs / JOB).resolve()


@pytest.mark.parametrize(
    "payload",
    [
        {"job": "../outside"},
        {"job": "job-0123456789ab/../../x"},
        {"job": "C:\\elsewhere\\job-0123456789ab"},
        {"job": 7},
        {"job_folder": "jobs/job-0123456789ab"},
        ["job-0123456789ab"],
    ],
)
def test_tampered_pointers_are_refused(jobs: Path, tmp_path: Path, payload) -> None:
    pointer = _pointer(tmp_path / "bad.json", payload)
    with pytest.raises(launcher.LauncherError):
        launcher.resolve_job(str(pointer))


def test_unknown_or_outside_jobs_are_refused(jobs: Path, tmp_path: Path) -> None:
    for value in ("job-ffffffffffff", "not-a-job", str(tmp_path / JOB)):
        with pytest.raises(launcher.LauncherError):
            launcher.resolve_job(value)


def _local_manifest(jobs: Path, run_dir: str) -> None:
    retained = jobs / JOB / ".engine-retained" / "runs" / JOB
    retained.mkdir(parents=True, exist_ok=True)
    (retained / "local_manifest.json").write_text(json.dumps({"run_dir": run_dir}))


def test_moved_jobs_detects_a_review_bound_to_a_former_location(jobs: Path) -> None:
    current = jobs / JOB / ".engine-retained" / "runs" / JOB
    _local_manifest(jobs, str(current))
    assert launcher.moved_jobs() == []
    _local_manifest(jobs, "C:\\old\\PDFScoreBar\\jobs\\" + JOB + "\\.engine-retained\\runs\\" + JOB)
    assert launcher.moved_jobs() == [jobs / JOB]


def test_run_and_serve_share_one_job_root_lock(jobs: Path) -> None:
    with exclusive_root(jobs):  # what tools.browser_jobs holds while serving
        with pytest.raises(launcher.LauncherError, match="in use"):
            with launcher.jobs_root_lock():
                pass
    with launcher.jobs_root_lock():
        with pytest.raises(BlockingIOError):
            with exclusive_root(jobs):
                pass


def test_browser_job_ids_fit_the_shared_pattern() -> None:
    ids = {new_job_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(launcher.JOB_ID.fullmatch(value) for value in ids)


def test_owned_call_reaps_descendants_left_by_the_child(tmp_path: Path, monkeypatch) -> None:
    from test_issue535_windows_native_support import (
        _SPAWN_GRANDCHILD,
        _alive,
        _grandchild_pid,
        _wait_for,
    )

    # A pipeline worker started with a plain subprocess call outlives its parent unless
    # the launcher owns the whole tree (#535).
    monkeypatch.setattr(launcher, "APP", Path(__file__).resolve().parents[1])
    pid_file = tmp_path / "grandchild.pid"
    command = [sys.executable, "-c", _SPAWN_GRANDCHILD, str(pid_file), "exit"]
    assert launcher.owned_call(command, dict(os.environ)) == 0
    grandchild = _grandchild_pid(pid_file)
    assert _wait_for(lambda: not _alive(grandchild))


# --- review checkpoints after the job folder moved ---------------------------------


def _moved_job(tmp_path: Path):
    """A job moved from old/<job> to new/<job>, with a checkpoint dependency recorded
    at the old absolute path."""

    job = tmp_path / "new" / JOB
    retained = job / ".engine-retained" / "runs" / JOB / "intermediate" / "page_001"
    retained.mkdir(parents=True)
    (job / "review").mkdir()
    dependency = retained / "numbering_base.json"
    dependency.write_bytes(b'{"pages": []}')
    old = str(tmp_path / "old" / JOB / ".engine-retained" / "runs" / JOB)
    recorded = os.path.join(old, "intermediate", "page_001", "numbering_base.json")
    return job, dependency, recorded


def _store(job: Path, recorded: str, expected: str):
    from types import SimpleNamespace

    from tools.review_correction.history import CheckpointStore

    store = CheckpointStore(SimpleNamespace(root=job / "review"))
    store.get = lambda _id: {"source_context": {"dependencies": {recorded: expected}}}
    return store


def test_checkpoint_dependencies_follow_a_moved_job(tmp_path: Path) -> None:
    from tools.review_correction.history import digest

    job, dependency, recorded = _moved_job(tmp_path)
    store = _store(job, recorded, digest(dependency.read_bytes()))
    assert store.validate_dependencies("cp")["source_context"]
    manifest = store._relocated_context_manifest({"pages": [{"numbering": recorded}]})
    assert manifest == {"pages": [{"numbering": str(dependency)}]}


def test_moved_checkpoint_dependencies_still_need_identical_bytes(tmp_path: Path) -> None:
    job, _dependency, recorded = _moved_job(tmp_path)
    store = _store(job, recorded, "0" * 64)
    with pytest.raises(ValueError, match="Retained source dependency"):
        store.validate_dependencies("cp")


@pytest.mark.parametrize(
    "recorded",
    [
        "/elsewhere/other-job/.engine-retained/runs/job-ffffffffffff/x.json",  # another job
        "/elsewhere/{job}/.engine-retained/runs/{job}/../../../../secret.json",  # escape
        "/elsewhere/{job}/not-retained/x.json",  # outside the retained layout
    ],
)
def test_rebase_only_maps_this_jobs_retained_layout(tmp_path: Path, recorded: str) -> None:
    from tools.review_correction.history import rebase_retained_path

    job, _dependency, _recorded = _moved_job(tmp_path)
    assert rebase_retained_path(recorded.format(job=JOB), job) is None


@pytest.mark.parametrize("server_name", ["LocalHTTPServer", "LocalThreadingHTTPServer"])
def test_review_and_browser_servers_refuse_a_port_in_use(server_name: str) -> None:
    from http.server import BaseHTTPRequestHandler

    from tools.review_correction import server as review_server

    server_class = getattr(review_server, server_name)
    with server_class(("127.0.0.1", 0), BaseHTTPRequestHandler) as first:
        # On Windows SO_REUSEADDR used to let a second server share the port (#535).
        with pytest.raises(OSError):
            server_class(("127.0.0.1", first.server_port), BaseHTTPRequestHandler)
