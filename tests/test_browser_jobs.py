from __future__ import annotations

import hashlib
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

import pytest

from src.pipeline.engine_contract import ArtifactDescriptor, JobResult, JobStatus, ProgressEvent
from tools.browser_jobs.jobs import MAX_BYTES, Jobs, exclusive_root
from tools.browser_jobs.server import create_server
from tools.review_correction.history import atomic_bytes


@pytest.fixture
def local_app(tmp_path):
    running, release = Event(), Event()

    def run(pdf, output, pages, *, job_id_factory, on_progress):
        assert pdf.name == "score.pdf"
        job_id = job_id_factory()
        on_progress(ProgressEvent(job_id, 1, "stage_started", "input_validation"))
        running.set()
        assert release.wait(5)
        assert pages == [1]
        data = pdf.read_bytes()
        package = output / job_id
        reference = "final/score_score_numbered.pdf"
        atomic_bytes(package / reference, data)
        result = JobResult(
            job_id=job_id,
            status=JobStatus.SUCCEEDED,
            provenance=dict(engine_version="1", pipeline_version="1", source_commit="test"),
            pages=dict(requested=1, processed=1, skipped=0),
            artifacts=(
                ArtifactDescriptor(
                    artifact_id="final.pdf",
                    role="final.score_numbered_pdf",
                    location_kind="relative_path",
                    reference=reference,
                    media_type="application/pdf",
                    sha256=hashlib.sha256(data).hexdigest(),
                ),
            ),
        )
        atomic_bytes(package / "result.json", result.to_json().encode())

    jobs = Jobs(tmp_path, run_job=run)
    with create_server(jobs, port=0) as server:
        port = server.server_port
        origin = f"http://127.0.0.1:{port}"

        def request(method, url, body=None, headers=None):
            client = HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                client.request(method, url, body=body, headers=headers or {})
                response = client.getresponse()
                return response.status, response.read()
            finally:
                client.close()

        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield jobs, origin, request, running, release
        finally:
            release.set()
            server.shutdown()
            thread.join()
            jobs.close()


def wait_until_finished(jobs: Jobs):
    deadline = monotonic() + 5
    while jobs.active and monotonic() < deadline:
        sleep(0.01)
    assert not jobs.active


def test_queue_progress_result_restart_and_mixup(local_app):
    jobs, origin, request, running, release = local_app
    headers = {
        "Origin": origin,
        "Content-Type": "application/pdf",
        "X-PDF-Name": "%E6%A5%BD%E8%AD%9C.pdf",
        "X-PDF-Pages": "1",
    }
    status, body = request("POST", "/api/jobs", b"%PDF-first", headers)
    assert status == 200
    first = json.loads(body)["id"]
    assert running.wait(3)
    status, body = request("POST", "/api/jobs", b"%PDF-second", headers)
    assert status == 200
    second = json.loads(body)["id"]
    assert first != second
    assert request("POST", "/api/jobs", b"third", headers)[0] == 409
    listed = {job["id"]: job for job in json.loads(request("GET", "/api/jobs")[1])["jobs"]}
    assert listed[first]["filename"] == "楽譜.pdf"
    assert listed[first]["progress"]["stage_id"] == "input_validation"
    assert listed[second]["status"] == "queued"
    assert request("GET", f"/jobs/{first}/pdf")[0] == 404
    release.set()
    wait_until_finished(jobs)
    for job_id, pdf in ((first, b"%PDF-first"), (second, b"%PDF-second")):
        assert request("GET", f"/jobs/{job_id}/pdf") == (200, pdf)
    restarted = Jobs(jobs.root)
    try:
        assert {job["id"] for job in restarted.list()} == {first, second}
        assert restarted.artifact(first, "final.score_numbered_pdf").read_bytes() == b"%PDF-first"
    finally:
        restarted.close()
    result = jobs.root / second / "result.json"
    saved = result.read_bytes()
    result.write_bytes((jobs.root / first / "result.json").read_bytes())
    assert request("GET", f"/jobs/{second}/pdf")[0] == 404
    result.write_bytes(saved)
    pdf = jobs.root / second / "final/score_score_numbered.pdf"
    pdf.unlink()
    pdf.symlink_to(jobs.root / first / "final/score_score_numbered.pdf")
    assert request("GET", f"/jobs/{second}/pdf")[0] == 404
    assert request("GET", f"/jobs/{first}/pdf") == (200, b"%PDF-first")


def test_loopback_and_upload_validation(local_app):
    jobs, origin, request, _, _ = local_app
    headers = {"Origin": origin, "Content-Type": "application/pdf", "X-PDF-Name": "score.pdf"}
    assert request("GET", "/api/jobs", headers={"Host": "example.test"})[0] == 403
    assert request("GET", "/api/jobs", headers={"Origin": "null"})[0] == 403
    for changes, expected in [
        ({"Origin": "https://example.test"}, 403),
        ({"Origin": ""}, 403),
        ({"Content-Type": "text/plain"}, 415),
        ({"Content-Length": str(MAX_BYTES + 1)}, 413),
        ({"X-PDF-Name": "..%2Fscore.pdf"}, 400),
        ({"X-PDF-Name": "C%3A%5Cscore.pdf"}, 400),
        ({"X-PDF-Pages": "0,1"}, 400),
    ]:
        assert request("POST", "/api/jobs", b"x", {**headers, **changes})[0] == expected
    assert request("POST", "/api/jobs?config=secret", b"x", headers)[0] == 404
    assert request("GET", "/jobs/../pdf")[0] == 404
    assert jobs.list() == []


def test_interrupted_submission_and_exclusive_root(tmp_path: Path):
    with exclusive_root(tmp_path):
        with pytest.raises(BlockingIOError), exclusive_root(tmp_path):
            pass
    job_id = "job-" + "a" * 32
    metadata = tmp_path / ".browser-jobs" / job_id / "submission.json"
    atomic_bytes(metadata, b'{"filename":"score.pdf"}')
    jobs = Jobs(tmp_path)
    try:
        assert jobs.list() == [
            {
                "id": job_id,
                "filename": "score.pdf",
                "created_at": None,
                "status": "interrupted",
            }
        ]
    finally:
        jobs.close()


def test_corrupt_saved_jobs_do_not_break_listing_or_revisits(local_app):
    jobs, origin, request, _, release = local_app
    release.set()
    headers = {
        "Origin": origin,
        "Content-Type": "application/pdf",
        "X-PDF-Name": "score.pdf",
        "X-PDF-Pages": "1",
    }
    status, body = request("POST", "/api/jobs", b"%PDF-good", headers)
    assert status == 200
    good = json.loads(body)["id"]
    wait_until_finished(jobs)
    good_result = (jobs.root / good / "result.json").read_bytes()
    deep = b"[" * 100_000 + b"]" * 100_000
    valid_metadata = b'{"filename":"saved.pdf","created_at":"2026-01-01T00:00:00Z"}'
    bad_types = json.loads(good_result)
    bad_types["pages"]["requested"] = "1"
    corrupt = {
        "job-" + "1" * 32: (b'{"filename":{},"created_at":{}}', None),
        "job-" + "2" * 32: (b'{"filename":["x"],"created_at":5}', None),
        "job-" + "3" * 32: (valid_metadata, json.dumps(bad_types).encode()),
        "job-" + "4" * 32: (valid_metadata, deep),
        "job-" + "5" * 32: (deep, deep),
        "job-" + "6" * 32: (deep, None),
    }
    for job_id, (metadata, result) in corrupt.items():
        atomic_bytes(jobs.uploads / job_id / "submission.json", metadata)
        if result is not None:
            atomic_bytes(jobs.root / job_id / "result.json", result)
    saved = {path: path.read_bytes() for path in jobs.root.rglob("*.json")}

    status, body = request("GET", "/api/jobs")
    assert status == 200
    listed = {job["id"]: job for job in json.loads(body)["jobs"]}
    restarted = Jobs(jobs.root)
    try:
        assert {job["id"]: job for job in restarted.list()} == listed
    finally:
        restarted.close()
    assert listed[good]["status"] == "succeeded"
    assert listed[good]["pdf"] == f"/jobs/{good}/pdf"
    for job_id in ("job-" + "1" * 32, "job-" + "2" * 32):
        assert listed[job_id] == {
            "id": job_id,
            "filename": job_id,
            "created_at": None,
            "status": "interrupted",
        }
    for job_id in ("job-" + "3" * 32, "job-" + "4" * 32, "job-" + "5" * 32):
        assert listed[job_id]["status"] == "failed"
        assert listed[job_id]["error"] == {"code": "invalid_saved_result"}
        assert "pdf" not in listed[job_id] and "review" not in listed[job_id]
        assert request("GET", f"/jobs/{job_id}/pdf")[0] == 404
    assert listed["job-" + "3" * 32]["filename"] == "saved.pdf"
    assert listed["job-" + "5" * 32]["filename"] == "job-" + "5" * 32
    assert "job-" + "6" * 32 not in listed
    assert request("GET", f"/jobs/{good}/pdf") == (200, b"%PDF-good")
    assert {path: path.read_bytes() for path in jobs.root.rglob("*.json")} == saved
