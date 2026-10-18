import hashlib
import http.client
import json
from pathlib import Path
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
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    final = run / "final" / f"{payload.get('output_name', 'corrected')}_score_numbered.pdf"
    final.write_bytes(b"%PDF-1.4\nexample")
    (run / "review" / "correction_summary.json").write_text(json.dumps({"final_pdf": str(final)}))
    return run


def _request_with_headers(server, method, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    conn.request(method, path)
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


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


def test_startup_failure_after_begin_apply_is_recorded_and_retryable(tmp_path, monkeypatch):
    app = _application(tmp_path)
    from tools.review_correction import application

    class FailingThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("thread start failed")

    with monkeypatch.context() as patch:
        patch.setattr(application, "Thread", FailingThread)
        with pytest.raises(RuntimeError, match="thread start failed"):
            app.start()

    snap = app.package.state.snapshot()
    assert snap["package"]["status"] == "error"
    assert snap["states"][0]["application_status"] == "error"
    assert app.process_lock is None
    assert not app.lock.locked()

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    assert app.package.state.snapshot()["package"]["current_result"] is not None


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
    assert (
        _request(
            server,
            "POST",
            "/api/save",
            {"page": 0, "correction_type": "barline_construction", "items": []},
        )[0]
        == 200
    )
    assert _request(server, "POST", "/api/apply", {})[0] == 200
    server.application.thread.join(5)
    status, headers, content = _request_with_headers(
        server, "GET", "/api/result?path=/other/result.pdf"
    )
    assert status == 200 and content.startswith(b"%PDF-")
    assert headers["Content-Disposition"] == (
        "inline; filename=\"corrected_score_numbered.pdf\"; filename*=UTF-8''corrected_score_numbered.pdf"
    )
    state = json.loads(_request(server, "GET", "/api/state")[1])
    assert state["package"]["current_result"]["final_pdf"] == str(server.application.result())


def test_application_carries_handoff_output_name_into_apply_snapshot(tmp_path, monkeypatch):
    app = _application(tmp_path)
    payload = json.loads(app.handoff.read_text(encoding="utf-8"))
    payload["output_name"] = "Festival_Overture"
    app.handoff.write_text(json.dumps(payload), encoding="utf-8")
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)

    snapshot = app.root / "attempt_0001" / "input_review" / "manual_correction_input.json"
    assert json.loads(snapshot.read_text(encoding="utf-8"))["output_name"] == "Festival_Overture"
    assert app.result().name == "Festival_Overture_score_numbered.pdf"


def test_application_recovers_name_from_existing_legacy_final_pdf(tmp_path, monkeypatch):
    app = _application(tmp_path)
    old_final = app.package.root.parent / "final" / "Festival_Overture_score_numbered.pdf"
    old_final.parent.mkdir(parents=True)
    old_final.write_bytes(b"%PDF-1.4\nold output")
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)

    snapshot = app.root / "attempt_0001" / "input_review" / "manual_correction_input.json"
    assert json.loads(snapshot.read_text(encoding="utf-8"))["output_name"] == "Festival_Overture"
    assert app.result().name == "Festival_Overture_score_numbered.pdf"


def test_application_does_not_recover_generic_score_from_legacy_final_pdf(tmp_path, monkeypatch):
    app = _application(tmp_path)
    old_final = app.package.root.parent / "final" / "score_score_numbered.pdf"
    old_final.parent.mkdir(parents=True)
    old_final.write_bytes(b"%PDF-1.4\nold output")
    from tools.review_correction import application

    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)

    snapshot = app.root / "attempt_0001" / "input_review" / "manual_correction_input.json"
    assert "output_name" not in json.loads(snapshot.read_text(encoding="utf-8"))
    assert app.result().name == "corrected_score_numbered.pdf"


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


def test_end_to_end_review_save_apply_and_download_preserves_pdf_and_filename(tmp_path):
    from threading import Thread

    import fitz
    from PIL import Image, ImageDraw

    from src.pipeline.review.manual_correction_materializer import (
        materialize_manual_correction_review_package,
    )
    from tools.review_correction.server import create_server

    run_root = tmp_path / "source_run"
    page_id = "page_001"
    image_path = run_root / "inputs" / "images" / f"{page_id}.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (300, 200), "white").save(image_path)

    staff_mask_path = run_root / "intermediate" / page_id / "staff_mask.png"
    staff_mask_path.parent.mkdir(parents=True)
    mask_img = Image.new("L", (300, 200), 0)
    draw = ImageDraw.Draw(mask_img)
    for y in (60, 70, 80, 90, 100):
        draw.line([(80, y), (260, y)], fill=255, width=2)
    mask_img.save(staff_mask_path)

    barlines = [
        {"barline_location": [90, 60, 92, 100]},
        {"barline_location": [160, 60, 162, 100]},
        {"barline_location": [240, 60, 242, 100]},
    ]
    barlines_path = run_root / "intermediate" / page_id / "barlines.json"
    barlines_path.write_text(json.dumps({"boxes": barlines}), encoding="utf-8")

    (run_root / "intermediate" / page_id / "overrides_mmr.json").write_text(
        json.dumps({"measure_overrides": []}), encoding="utf-8"
    )

    numbering_payload = {
        "pages": [
            {
                "page_number": 1,
                "width": 300,
                "height": 200,
                "systems": [
                    {
                        "staves": [{"bbox": [80, 60, 260, 100]}],
                        "measures": [
                            {"number": 1, "bbox": [90, 60, 160, 100]},
                            {"number": 2, "bbox": [160, 60, 240, 100]},
                        ],
                    }
                ],
                "empty_systems": [],
            }
        ],
        "numbering_metadata": {"page_index": 0, "start_number": 1, "next_number": 3},
    }
    outputs_dir = run_root / "outputs" / page_id
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "numbering_final.json").write_text(
        json.dumps(numbering_payload), encoding="utf-8"
    )
    Image.new("RGB", (300, 200), "white").save(outputs_dir / "numbering_overlay.png")
    (run_root / "intermediate" / page_id / "numbering_base.json").write_text(
        json.dumps(numbering_payload), encoding="utf-8"
    )

    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "source_run",
                "config": {
                    "inputs": {"pdf_path": "/scores/Symphony No. 1.pdf"},
                    "steps": {"mmr_overrides": False},
                    "outputs": {},
                },
                "pages": [
                    {
                        "page_id": page_id,
                        "image_path": str(image_path),
                        "staff_mask": str(staff_mask_path),
                        "barlines_json": str(barlines_path),
                        "page_size_points": [72.0, 48.0],
                        "status": {"page_index": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    review_root = run_root / "review"
    materialize_manual_correction_review_package(run_root=run_root, review_root=review_root)
    handoff = review_root / "manual_correction_input.json"

    server = create_server(handoff, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        save_status, _ = _request(
            server,
            "POST",
            "/api/save",
            {
                "page": 0,
                "correction_type": "mmr_measure_span",
                "items": [
                    {
                        "op": "set_measure_span",
                        "page": 0,
                        "system": 0,
                        "measure": 0,
                        "measure_span": 4,
                    }
                ],
            },
        )
        assert save_status == 200

        apply_status, _ = _request(server, "POST", "/api/apply", {})
        assert apply_status == 200
        server.application.thread.join(10)

        state = json.loads(_request(server, "GET", "/api/state")[1])
        mmr_state = next(s for s in state["states"] if s["correction_type"] == "mmr_measure_span")
        assert mmr_state["application_status"] == "current"
        result_path = server.application.result()
        assert state["package"]["current_result"]["final_pdf"] == str(result_path)
        assert result_path.name == "Symphony_No._1_score_numbered.pdf"

        corrected_run = Path(state["package"]["current_result"]["corrected_run"])
        corrected_numbering = json.loads(
            (corrected_run / "outputs" / page_id / "numbering_final.json").read_text(
                encoding="utf-8"
            )
        )
        measures = corrected_numbering["pages"][0]["systems"][0]["measures"]
        assert [m["number"] for m in measures] == [1, 5]

        status, headers, content = _request_with_headers(server, "GET", "/api/result")
        assert status == 200
        assert headers["Content-Disposition"] == (
            'inline; filename="Symphony_No._1_score_numbered.pdf"; '
            "filename*=UTF-8''Symphony_No._1_score_numbered.pdf"
        )
        with fitz.open(stream=content, filetype="pdf") as document:
            assert document.page_count == 1
            assert document[0].rect.width == pytest.approx(72.0)
            assert document[0].rect.height == pytest.approx(48.0)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
