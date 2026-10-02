import hashlib
import json
from threading import Event

import pytest
from test_review_correction_server import _handoff, _request
from test_review_correction_server import review_server as _review_server

from tools.review_correction.application import CorrectionApplication
from tools.review_correction.server import ReviewPackage


def _application(tmp_path):
    handoff = _handoff(tmp_path)
    manifest = handoff.parent.parent / "manifest.json"
    manifest.write_text(json.dumps({"config": {"inputs": {}, "steps": {}, "outputs": {}}}))
    package = ReviewPackage(handoff)
    return CorrectionApplication(package, handoff)


def _fake_engine(handoff, **kwargs):
    assert kwargs["generate_final_pdf"] is True
    assert kwargs["overwrite"] is False
    run = kwargs["output_root"] / kwargs["run_id"]
    (run / "final").mkdir(parents=True)
    (run / "review").mkdir()
    final = run / "final" / "score_numbered.pdf"
    final.write_bytes(b"%PDF-1.4\nexample")
    (run / "review" / "correction_summary.json").write_text(json.dumps({"final_pdf": str(final)}))
    return run


def test_apply_snapshots_inputs_and_records_exact_success(tmp_path, monkeypatch):
    app = _application(tmp_path)
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    identity = app.package.state.capture_identity()
    app.start()
    app.thread.join(5)
    snap = app.package.state.snapshot()
    assert snap["package"]["current_result"]["identity"] == identity["identity"]
    final = app.result()
    assert (
        hashlib.sha256(final.read_bytes()).hexdigest()
        == snap["package"]["current_result"]["final_pdf_sha256"]
    )
    assert (
        app.root / "attempt_0001" / "input_review" / "pages/page_001/source.png"
    ).read_bytes() == b"image"
    assert (app.root / "attempt_0001" / "consumed_inputs.json").is_file()
    final.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        app.result()


def test_failed_apply_and_pdf_generation_preserve_last_success(tmp_path, monkeypatch):
    app = _application(tmp_path)
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    previous = app.package.state.snapshot()["package"]["last_successful_result"]

    def fail(*args, **kwargs):
        run = kwargs["output_root"] / kwargs["run_id"]
        run.mkdir()
        raise RuntimeError("PDF generation failed after run start")

    monkeypatch.setattr(application, "apply_corrections_and_rerun", fail)
    app.start()
    app.thread.join(5)
    snap = app.package.state.snapshot()
    assert snap["package"]["last_successful_result"] == previous
    assert snap["package"]["status"] == "error"
    assert app.result().is_file()
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    assert app.package.state.snapshot()["package"]["current_result"]["corrected_run"].endswith(
        "attempt_0003/corrected"
    )


def test_duplicate_apply_rejected_and_inputs_cannot_change_in_flight(tmp_path, monkeypatch):
    app = _application(tmp_path)
    from tools.review_correction import application

    entered, release = Event(), Event()

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return _fake_engine(*args, **kwargs)

    monkeypatch.setattr(application, "apply_corrections_and_rerun", slow)
    app.start()
    assert entered.wait(5)
    with pytest.raises(ValueError, match="already"):
        app.start()
    (app.package.root / "pages/page_001/source.png").write_bytes(b"new source")
    release.set()
    app.thread.join(5)
    snap = app.package.state.snapshot()
    assert snap["package"]["last_successful_result"] is None
    assert snap["package"]["status"] == "error"


def test_application_output_symlink_rejected(tmp_path):
    app = _application(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    app.root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="directory"):
        app.start()
    assert list(outside.iterdir()) == []


@pytest.fixture
def application_server(tmp_path):
    yield from _review_server.__wrapped__(tmp_path)


def test_apply_http_rejects_path_substitution_and_exposes_only_own_result(
    application_server, monkeypatch
):
    server, handoff = application_server
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    for payload in (
        {"handoff": "/other/review/manual_correction_input.json"},
        {"overwrite": True},
        {"run_id": "other"},
    ):
        assert _request(server, "POST", "/api/apply", payload)[0] == 400
    assert not server.application.root.exists()
    assert _request(server, "POST", "/api/apply", {})[0] == 200
    server.application.thread.join(5)
    status, content = _request(server, "GET", "/api/result?path=/other/result.pdf")
    assert status == 200 and content.startswith(b"%PDF-")
    state = json.loads(_request(server, "GET", "/api/state")[1])
    assert state["package"]["current_result"]["final_pdf"] == str(server.application.result())


def test_apply_http_blocks_save_and_duplicate_while_running(application_server, monkeypatch):
    server, handoff = application_server
    from tools.review_correction import application

    entered, release = Event(), Event()

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return _fake_engine(*args, **kwargs)

    monkeypatch.setattr(application, "apply_corrections_and_rerun", slow)
    try:
        assert _request(server, "POST", "/api/apply", {})[0] == 200
        assert entered.wait(5)
        assert _request(server, "POST", "/api/apply", {})[0] == 400
        assert (
            _request(
                server,
                "POST",
                "/api/save",
                {"page": 0, "correction_type": "barline_construction", "items": []},
            )[0]
            == 400
        )
    finally:
        release.set()
        server.application.thread.join(5)
