"""Issue #535: the portable launcher's job pointers, relocation and job-root lock.

These run on every platform: the launcher logic is plain path/JSON handling, and the
lock is the shared ``src.common.file_lock`` used by ``tools.browser_jobs``.
"""

from __future__ import annotations

import json
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
