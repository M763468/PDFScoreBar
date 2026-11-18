"""Local job storage and the runtime adapter used by the browser and launchers."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

from docker.distribution_job import run_local_job
from src.pipeline.engine_contract import JobResult, JobStatus
from src.pipeline.engine_input_safety import DEFAULT_JOB_SAFETY_POLICY
from tools.review_correction.history import atomic_bytes, encoded, now, package_path

JOB_ID = re.compile(r"job-[0-9a-f]{12,32}")
READY = {JobStatus.SUCCEEDED, JobStatus.REVIEW_REQUIRED}
MAX_BYTES = DEFAULT_JOB_SAFETY_POLICY.max_pdf_bytes
MAX_PAGES = DEFAULT_JOB_SAFETY_POLICY.max_selected_pages


@contextmanager
def exclusive_root(root: Path):
    """Keep one browser service per output root, including during shutdown."""
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".browser-jobs.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Jobs:
    def __init__(self, root: Path, *, run_job=run_local_job):
        self.root = root.resolve()
        self.uploads = package_path(self.root, ".browser-jobs")
        self.uploads.mkdir(exist_ok=True)
        self.run_job = run_job
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.active = {}
        self.lock = Lock()

    def close(self):
        self.worker.shutdown()

    def submit(self, stream, size: int, name: str, pages: list[int]) -> str:
        with self.lock:
            if len(self.active) >= 2:
                raise OverflowError("Wait for a submitted job to finish")
            job_id = f"job-{uuid4().hex}"
            if (self.root / job_id).exists():
                raise FileExistsError(job_id)
            directory = self.uploads / job_id
            directory.mkdir(mode=0o700)
            self.active[job_id] = {"status": "uploading"}
        try:
            # Only the display name comes from the browser.
            pdf = directory / "score.pdf"
            with pdf.open("xb") as output:
                remaining = size
                while remaining:
                    chunk = stream.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("Incomplete PDF upload")
                    output.write(chunk)
                    remaining -= len(chunk)
            atomic_bytes(
                directory / "submission.json",
                encoded(
                    {
                        "filename": name,
                        "created_at": now(),
                        "selected_pages": pages,
                    }
                ),
            )
            with self.lock:
                self.active[job_id] = {"status": "queued"}
            self.worker.submit(self._run, job_id, pdf, pages)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            with self.lock:
                self.active.pop(job_id, None)
            raise
        return job_id

    def _run(self, job_id: str, pdf: Path, pages: list[int]):
        with self.lock:
            self.active[job_id] = {"status": "running"}

        def progress(event):
            if event.job_id == job_id and not event.terminal:
                with self.lock:
                    self.active[job_id] = {"status": "running", "progress": event.to_dict()}

        try:
            self.run_job(pdf, self.root, pages, job_id_factory=lambda: job_id, on_progress=progress)
            self.result(job_id)
        except Exception:
            logging.exception("Local job %s failed before result publication", job_id)
            try:
                atomic_bytes(pdf.with_name("failed"), b"")
            except OSError:
                logging.exception("Could not record failure for %s", job_id)
        finally:
            with self.lock:
                self.active.pop(job_id, None)

    def result(self, job_id: str) -> JobResult:
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("Invalid job ID")
        path = package_path(self.root, f"{job_id}/result.json")
        result = JobResult.from_json(path.read_text(encoding="utf-8"))
        if result.job_id != job_id:
            raise ValueError("Result belongs to a different job")
        return result

    def artifact(self, job_id: str, role: str) -> Path:
        result = self.result(job_id)
        if result.status not in READY:
            raise ValueError("The job has no successful result")
        descriptors = [item for item in result.artifacts if item.role == role]
        if len(descriptors) != 1:
            raise ValueError("Expected one job artifact")
        item = descriptors[0]
        path = package_path(self.root / job_id, item.reference)
        if role == "review.manual_correction_input":
            if item.reference != "review/manual_correction_input.json":
                raise ValueError("Invalid review reference")
            handoff = json.loads(path.read_text(encoding="utf-8"))
            if handoff.get("source_job_id") != job_id:
                raise ValueError("Review package belongs to a different job")
            raw_manifest = handoff.get("source_manifest")
            allowed = f"../.engine-retained/runs/{job_id}/local_manifest.json"
            if raw_manifest != allowed:
                raise ValueError("Expected a prepared local review manifest")
            package_path(self.root / job_id, allowed[3:]).stat()
        elif path.parent != self.root / job_id / "final" or path.suffix != ".pdf":
            raise ValueError("Invalid numbered PDF reference")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item.sha256:
                raise ValueError("Artifact digest mismatch")
        return path

    def list(self) -> list[dict]:
        ids = {
            path.name
            for parent in (self.root, self.uploads)
            for path in parent.iterdir()
            if JOB_ID.fullmatch(path.name) and not path.is_symlink() and path.is_dir()
        }
        with self.lock:
            active = self.active.copy()
        jobs = []
        for job_id in ids:
            try:
                metadata_path = package_path(self.uploads, f"{job_id}/submission.json")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not isinstance(metadata, dict):
                    raise ValueError("Invalid submission metadata")
            except (OSError, ValueError):
                metadata = {}
            job = {
                "id": job_id,
                "filename": metadata.get("filename", job_id),
                "created_at": metadata.get("created_at"),
                "status": "interrupted",
            }
            if job_id in active:
                if metadata:
                    jobs.append({**job, **active[job_id]})
                continue
            try:
                result = self.result(job_id)
            except FileNotFoundError:
                if not metadata:
                    continue
                if package_path(self.uploads, f"{job_id}/failed").is_file():
                    job.update(status="failed", error={"code": "local_job_failed"})
            except (OSError, ValueError):
                job.update(status="failed", error={"code": "invalid_saved_result"})
            else:
                job.update(status=result.status.value, pages=result.pages)
                if result.failure:
                    job["error"] = {"code": result.failure.code}
                if result.status in READY:
                    job["pdf"] = f"/jobs/{job_id}/pdf"
                    job["review"] = f"/jobs/{job_id}/review/"
            jobs.append(job)
        return sorted(jobs, key=lambda job: (job["created_at"] or "", job["id"]), reverse=True)
