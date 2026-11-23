from __future__ import annotations

import hashlib
import json
import re
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


def _write_ready_job(root: Path, job_id: str, *, browser_submission: bool) -> None:
    job_dir = root / job_id
    review = job_dir / "review"
    page = review / "pages" / "page_001"
    page.mkdir(parents=True)
    (page / "source.png").write_bytes(b"image")
    for name in ("numbering_final.json", "mmr_overrides.json", "barlines_review.json"):
        (page / name).write_text("{}", encoding="utf-8")
    (page / "numbering_final.json").write_text(json.dumps({"systems": [{"index": 0}]}))
    retained_manifest = job_dir / ".engine-retained" / "runs" / job_id / "local_manifest.json"
    retained_manifest.parent.mkdir(parents=True)
    retained_manifest.write_text(
        json.dumps({"config": {"inputs": {}, "steps": {}, "outputs": {}}}), encoding="utf-8"
    )
    handoff_bytes = json.dumps(
        {
            "schema_version": 1,
            "kind": "manual_correction_input",
            "source_job_id": job_id,
            "source_manifest": f"../.engine-retained/runs/{job_id}/local_manifest.json",
            "pages": [
                {
                    "page_id": "page_001",
                    "page_number": 1,
                    "source_image": "pages/page_001/source.png",
                    "numbering_final": "pages/page_001/numbering_final.json",
                    "mmr_overrides": "pages/page_001/mmr_overrides.json",
                    "barlines_review": "pages/page_001/barlines_review.json",
                    "correction_output": "corrections",
                }
            ],
        }
    ).encode("utf-8")
    handoff_path = review / "manual_correction_input.json"
    atomic_bytes(handoff_path, handoff_bytes)
    result = JobResult(
        job_id=job_id,
        status=JobStatus.SUCCEEDED,
        provenance=dict(engine_version="1", pipeline_version="1", source_commit="test"),
        pages=dict(requested=1, processed=1, skipped=0),
        artifacts=(
            ArtifactDescriptor(
                artifact_id="review.input",
                role="review.manual_correction_input",
                location_kind="relative_path",
                reference="review/manual_correction_input.json",
                media_type="application/json",
                sha256=hashlib.sha256(handoff_bytes).hexdigest(),
            ),
        ),
    )
    atomic_bytes(job_dir / "result.json", result.to_json().encode("utf-8"))
    if browser_submission:
        atomic_bytes(
            root / ".browser-jobs" / job_id / "submission.json",
            json.dumps({"filename": "score.pdf", "created_at": "2026-01-01T00:00:00Z"}).encode(
                "utf-8"
            ),
        )


def _assert_no_browser_path_leak(reason: str, body: bytes, *needles: str) -> None:
    text = f"{reason}\n{body.decode('utf-8', errors='replace')}"
    assert not re.search(
        r"resumed_sessions|manual_correction_input\.json|Traceback|\[Errno|\[WinError"
        r"|(?:^|[\s'\"(\[{:=])[A-Za-z]:[\\/]|\\\\"
        r"|(?:^|[\s'\"(\[{:=])/(?:home|tmp|var|opt|workspace|Users|mnt|private)/",
        text,
        re.IGNORECASE,
    ), text
    for needle in needles:
        if len(needle) > 1:
            assert needle.lower() not in text.lower(), (needle, text)


def test_cross_job_review_session_rejected_without_path_disclosure(tmp_path: Path):
    job_a = "job-" + "a" * 12
    job_b = "job-" + "b" * 12
    job_c = "job-" + "c" * 12
    _write_ready_job(tmp_path, job_a, browser_submission=True)
    _write_ready_job(tmp_path, job_b, browser_submission=False)

    session_a = "s_" + "e" * 32
    session_review = tmp_path / job_a / "review" / "resumed_sessions" / session_a / "review"
    session_page = session_review / "pages" / "page_001"
    session_page.mkdir(parents=True)
    (session_page / "source.png").write_bytes(b"image")
    for name in ("numbering_final.json", "mmr_overrides.json", "barlines_review.json"):
        (session_page / name).write_text("{}", encoding="utf-8")
    (session_page / "numbering_final.json").write_text(json.dumps({"systems": [{"index": 0}]}))
    (session_review / "manual_correction_input.json").write_text(
        (tmp_path / job_a / "review" / "manual_correction_input.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    atomic_bytes(
        tmp_path / ".browser-jobs" / job_c / "submission.json",
        b'{"filename":"broken.pdf","created_at":"2026-01-01T00:00:00Z"}',
    )
    atomic_bytes(tmp_path / ".browser-jobs" / job_c / "failed", b"")

    jobs = Jobs(tmp_path)
    try:
        with create_server(jobs, port=0) as server:
            port = server.server_port
            origin = f"http://127.0.0.1:{port}"

            def request(method, url, body=None, headers=None):
                client = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    client.request(method, url, body=body, headers=headers or {})
                    response = client.getresponse()
                    return response.status, response.reason, response.read()
                finally:
                    client.close()

            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                assert (
                    request("GET", f"/jobs/{job_a}/review/api/state?session={session_a}")[0] == 200
                )
                assert (
                    request("GET", f"/jobs/{job_a}/review/api/pages?session={session_a}")[0] == 200
                )
                save_headers = {"Origin": origin, "Content-Type": "application/json"}
                save_body = json.dumps(
                    {"page": 0, "correction_type": "barline_construction", "items": []}
                ).encode("utf-8")
                assert (
                    request(
                        "POST",
                        f"/jobs/{job_a}/review/api/save?session={session_a}",
                        body=save_body,
                        headers=save_headers,
                    )[0]
                    == 200
                )

                for method, route, body, headers in (
                    ("GET", f"/jobs/{job_b}/review/api/state?session={session_a}", None, {}),
                    ("GET", f"/jobs/{job_b}/review/api/pages?session={session_a}", None, {}),
                    ("GET", f"/jobs/{job_b}/review/api/checkpoints?session={session_a}", None, {}),
                    (
                        "POST",
                        f"/jobs/{job_b}/review/api/save?session={session_a}",
                        save_body,
                        save_headers,
                    ),
                    (
                        "POST",
                        f"/jobs/{job_b}/review/api/apply?session={session_a}",
                        b"{}",
                        save_headers,
                    ),
                    ("GET", f"/jobs/{job_c}/review/api/state?session={session_a}", None, {}),
                ):
                    status, reason, content = request(method, route, body=body, headers=headers)
                    assert status == 404
                    _assert_no_browser_path_leak(
                        reason,
                        content,
                        str(tmp_path),
                        tmp_path.name,
                        job_a,
                        job_b,
                        job_c,
                        session_a,
                    )

                for route in (
                    f"/jobs/{job_b}/review/api/state?session=../../other",
                    f"/jobs/{job_b}/review/api/state?session=",
                ):
                    status, reason, content = request("GET", route)
                    assert status == 400
                    _assert_no_browser_path_leak(
                        reason,
                        content,
                        str(tmp_path),
                        tmp_path.name,
                        job_b,
                    )

                assert (
                    request(
                        "POST",
                        f"/jobs/{job_b}/review/api/save",
                        body=save_body,
                        headers={
                            "Origin": "https://example.test",
                            "Content-Type": "application/json",
                        },
                    )[0]
                    == 403
                )
                status, reason, content = request(
                    "POST",
                    "/api/jobs",
                    body=b"%PDF-1.4",
                    headers={
                        "Origin": origin,
                        "Content-Type": "application/pdf",
                        "X-PDF-Name": "%FF.pdf",
                    },
                )
                assert status == 400
                assert "Choose a PDF filename" in reason
                body_text = content.decode("utf-8", errors="replace").lower()
                assert "codec" not in body_text and "can't decode" not in body_text
            finally:
                server.shutdown()
                thread.join()
    finally:
        jobs.close()
