"""Checkpoint persistence, isolated resume, and exact application provenance."""

import base64
import json
from pathlib import Path
from threading import Event

import fitz
import pytest
from PIL import Image
from test_review_correction_application import _application
from test_review_correction_server import (
    _handoff,
    _request,
    review_server,  # noqa: F401
)

from tools.review_correction import application
from tools.review_correction.history import digest, encoded
from tools.review_correction.resume import create_session
from tools.review_correction.server import ReviewPackage


def _pdf_package(tmp_path):
    handoff = _handoff(tmp_path)
    source = tmp_path / "original.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=260)
        for y in range(100, 125, 5):
            page.draw_line((60, y), (180, y))
        doc.save(source)
        page.get_pixmap().save(handoff.parent / "pages/page_001/source.png")
        note = page.add_ink_annot([[(130, 170), (145, 175)]])
        note.update()
        page.set_cropbox(fitz.Rect(10, 10, 190, 250))
        doc.save(tmp_path / "annotated.pdf")
    manifest = {
        "config": {"inputs": {}, "steps": {}, "outputs": {}},
        "pages": [
            {
                "source_reference": {
                    "source_page": 0,
                    "source_document": {
                        "path": str(source),
                        "sha256": digest(source.read_bytes()),
                    },
                }
            }
        ],
    }
    (handoff.parent.parent / "manifest.json").write_bytes(encoded(manifest))
    return ReviewPackage(handoff), (tmp_path / "annotated.pdf").read_bytes()


def _checkpoint(package):
    with package.history.transaction():
        return package.history.capture()


def test_null_source_reference_preserves_correction_save_and_apply(tmp_path, monkeypatch):
    from test_review_correction_application import _fake_engine

    app = _application(tmp_path)
    manifest = app.package.root.parent / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["pages"] = [{"source_reference": None}]
    manifest.write_bytes(encoded(payload))
    package = app.package
    package.record_correction(0, "barline_construction", [])
    checkpoint = _checkpoint(package)
    assert "source_pdf" not in package.history.get(checkpoint)["source_context"]
    assert package.history.list()[0]["can_resume_pdf"] is False
    restored = tmp_path / "restored/review"
    package.history.materialize(checkpoint, restored)
    restored_package = ReviewPackage(restored / "manual_correction_input.json")
    assert (
        restored_package.state.capture_identity()["corrections_identity"]
        == package.state.capture_identity()["corrections_identity"]
    )
    with pytest.raises(ValueError, match="no verified original PDF"):
        create_session(package, checkpoint, b"%PDF-no-provenance")
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    assert app.result().is_file()
    assert package.state.snapshot()["package"]["current_result"] is not None


def test_immutable_checkpoints_survive_restart_and_all_four_correction_types(tmp_path):
    package = ReviewPackage(_handoff(tmp_path))
    empty = _checkpoint(package)
    for kind, item in [
        ("mmr_measure_span", {"page": 0, "system": 0, "measure": 0, "span": 6}),
        ("measure_construction", {"page": 0, "system": 0, "op": "split", "x": 100}),
        ("barline_construction", {"page": 0, "system": 0, "op": "add", "x": 100}),
        ("movement_boundary", {"page": 0, "system": 0, "op": "boundary"}),
    ]:
        package.record_correction(0, kind, [item])
    saved = _checkpoint(package)
    assert saved != empty
    restarted = ReviewPackage(package.handoff_path)
    assert len(restarted.history.list()) == 5
    assert _checkpoint(restarted) == saved
    copied = tmp_path / "restored/review"
    restarted.history.materialize(saved, copied)
    restored = ReviewPackage(copied / "manual_correction_input.json")
    assert (
        restored.state.capture_identity()["corrections_identity"]
        == package.state.capture_identity()["corrections_identity"]
    )
    assert restored.state.snapshot()["package"]["last_successful_result"] is None
    assert restarted.history.get(empty)["identity"] != restarted.history.get(saved)["identity"]


def test_checkpoint_corruption_symlink_and_dependency_changes_fail_closed(tmp_path):
    app = _application(tmp_path)
    package = app.package
    cp = _checkpoint(package)
    ref = package.history.get(cp)["files"]["manual_correction_input.json"]
    blob = package.history.root / "blobs" / ref["sha256"]
    original = blob.read_bytes()
    blob.write_bytes(b"broken")
    with pytest.raises(ValueError, match="changed"):
        package.history.get(cp)
    blob.write_bytes(original)
    blob.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(original)
    blob.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        package.history.get(cp)
    with pytest.raises(ValueError, match="ID"):
        package.history.get("../../outside")


def test_failed_checkpoint_save_rolls_back_corrections(tmp_path, monkeypatch):
    package = ReviewPackage(_handoff(tmp_path))
    package.record_correction(0, "barline_construction", [])
    previous = {rel: path.read_bytes() for rel, path in package.writes.items() if path.exists()}

    def fail(**kwargs):
        raise OSError("history disk full")

    monkeypatch.setattr(package.history, "capture", fail)
    with pytest.raises(OSError, match="disk full"):
        package.record_correction(
            0, "barline_construction", [{"page": 0, "system": 0, "op": "add", "x": 70}]
        )
    assert previous == {
        rel: path.read_bytes() for rel, path in package.writes.items() if path.exists()
    }
    assert package.state.snapshot()["package"]["status"] == "error"


def test_running_failure_and_interruption_survive_restart(tmp_path, monkeypatch):
    app = _application(tmp_path)
    entered, release = Event(), Event()

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise RuntimeError("engine failed")

    monkeypatch.setattr(application, "apply_corrections_and_rerun", slow)
    app.start()
    assert entered.wait(5)
    other = ReviewPackage(app.handoff)
    assert other.state.snapshot()["package"]["status"] == "applying"
    with pytest.raises(ValueError, match="generation"):
        other.record_correction(0, "barline_construction", [])
    release.set()
    app.thread.join(5)
    restarted = ReviewPackage(app.handoff)
    assert restarted.state.snapshot()["package"]["last_application"]["status"] == "failed"
    # A crash leaves running metadata but releases the OS file lock.
    metadata = restarted.state.metadata_path
    data = json.loads(metadata.read_text())
    data["last_application"] = {"status": "running"}
    metadata.write_bytes(encoded(data))
    recovered = ReviewPackage(app.handoff)
    assert recovered.state.snapshot()["package"]["last_application"]["status"] == "interrupted"
    assert recovered.state.snapshot()["package"]["current_result"] is None


def test_resume_sessions_are_independent_and_reject_unknown_background(tmp_path):
    package, pdf = _pdf_package(tmp_path)
    cp = _checkpoint(package)
    identity = package.state.capture_identity()
    first = create_session(package, cp, pdf)
    second = create_session(package, cp, pdf)
    assert first != second
    restored = ReviewPackage(
        package.root / f"resumed_sessions/{first}/review/manual_correction_input.json"
    )
    restored.record_correction(
        0, "barline_construction", [{"page": 0, "system": 0, "op": "add", "x": 90}]
    )
    assert package.state.capture_identity() == identity
    assert Image.open(restored.readable(restored.pages[0]["display_image"])).size == (200, 260)
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        doc[0].insert_text((40, 60), "unknown old number")
        unknown = doc.tobytes()
    before = sorted((package.root / "resumed_sessions").iterdir())
    with pytest.raises(ValueError, match="background"):
        create_session(package, cp, unknown)
    assert sorted((package.root / "resumed_sessions").iterdir()) == before
    assert digest(pdf) == json.loads(restored.handoff_path.read_text())["resume"]["input_sha256"]


def test_resumed_apply_uses_safe_layer_and_records_sidecar(tmp_path, monkeypatch):
    package, pdf = _pdf_package(tmp_path)
    session = create_session(package, _checkpoint(package), pdf)
    handoff = package.root / f"resumed_sessions/{session}/review/manual_correction_input.json"
    restored = ReviewPackage(handoff)

    def engine(handoff, **kwargs):
        assert kwargs["generate_final_pdf"] is False
        run = kwargs["output_root"] / kwargs["run_id"]
        (run / "review").mkdir(parents=True)
        (run / "review/correction_summary.json").write_text("{}")
        path = run / "outputs/page_001/numbering_final.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(
            encoded(
                {
                    "pages": [
                        {
                            "systems": [
                                {
                                    "staves": [{"bbox": [60, 100, 180, 125]}],
                                    "measures": [{"number": 12, "bbox": [60, 100, 180, 125]}],
                                }
                            ]
                        }
                    ]
                }
            )
        )
        return run

    monkeypatch.setattr(application, "apply_corrections_and_rerun", engine)
    app = application.CorrectionApplication(restored, handoff)
    app.start()
    app.thread.join(5)
    snap = restored.state.snapshot()
    assert snap["package"]["current_result"], snap
    with fitz.open(app.result()) as doc:
        assert doc[0].get_text().strip() == "12"
        assert len(list(doc[0].annots())) == 1
        assert doc[0].cropbox == fitz.Rect(10, 10, 190, 250)
    result = snap["package"]["current_result"]
    Path(result["number_layer_sidecar"]).write_bytes(b"bad")
    with pytest.raises(ValueError, match="sidecar"):
        app.result()


def test_history_http_rejects_paths_and_unverified_pdf(review_server):  # noqa: F811
    server, _ = review_server
    status, body = _request(server, "POST", "/api/checkpoints", {"label": "before edit"})
    assert status == 200
    cp = json.loads(body)["checkpoint_id"]
    assert _request(server, "GET", "/api/checkpoints")[0] == 200
    assert _request(server, "POST", "/api/checkpoints", {"path": "/tmp/other"})[0] == 400
    assert (
        _request(
            server,
            "POST",
            "/api/resume",
            {"checkpoint_id": cp, "pdf_base64": base64.b64encode(b"%PDF-1.4").decode()},
        )[0]
        == 400
    )
    assert _request(server, "GET", "/api/pages?session=../../other")[0] == 400


def test_retained_dependency_mutation_blocks_reusing_checkpoint(tmp_path):
    app = _application(tmp_path)
    retained = tmp_path / "retained.json"
    retained.write_text("{}")
    manifest = app.package.root.parent / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["pages"] = [{"retained_numbering": str(retained)}]
    manifest.write_bytes(encoded(payload))
    cp = _checkpoint(app.package)
    retained.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="dependency"):
        app.package.history.validate_dependencies(cp)
    with pytest.raises(ValueError, match="dependency"):
        _checkpoint(app.package)


def test_http_resume_session_survives_registry_reload_and_stays_isolated(review_server, tmp_path):  # noqa: F811
    server, _ = review_server
    package, pdf = _pdf_package(tmp_path / "pdf")
    server.package = package
    server.application = application.CorrectionApplication(package, package.handoff_path)
    cp = _checkpoint(package)
    status, body = _request(
        server,
        "POST",
        "/api/resume",
        {
            "checkpoint_id": cp,
            "pdf_base64": base64.b64encode(pdf).decode(),
        },
    )
    assert status == 200, body
    session = json.loads(body)["session"]
    query = "?session=" + session
    assert _request(server, "GET", "/api/pages" + query)[0] == 200
    server.sessions.clear()  # Same lazy-load path as server restart.
    assert _request(server, "GET", "/api/state" + query)[0] == 200
    original = package.state.capture_identity()
    assert (
        _request(
            server,
            "POST",
            "/api/save" + query,
            {
                "page": 0,
                "correction_type": "barline_construction",
                "items": [],
            },
        )[0]
        == 200
    )
    assert package.state.capture_identity() == original
    assert _request(server, "GET", "/file?path=resume/input.pdf&session=" + session)[0] == 403


def test_every_failed_and_successful_application_is_retained(tmp_path, monkeypatch):
    from test_review_correction_application import _fake_engine

    app = _application(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("retained failure")

    monkeypatch.setattr(application, "apply_corrections_and_rerun", fail)
    app.start()
    app.thread.join(5)
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    restarted = ReviewPackage(app.handoff)
    records = restarted.history.list_applications()
    assert [r["status"] for r in records] == ["failed", "succeeded"]
    assert records[0]["error"] == "retained failure"
    assert (
        records[1]["result"]["final_pdf_sha256"]
        == restarted.state.snapshot()["package"]["current_result"]["final_pdf_sha256"]
    )


def test_abandoned_history_requires_state_attestation_not_pdf_existence(tmp_path, monkeypatch):
    from test_review_correction_application import _fake_engine

    app = _application(tmp_path)
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    history = app.package.history
    record = history.application_record("attempt_0001")
    record.pop("result")
    record["status"] = "running"  # Simulate death after state commit, before journal commit.
    history.application_record("attempt_0001", record)
    history.application_record("attempt_0002", record)  # Same identity/PDF, different attempt.
    recovered = ReviewPackage(app.handoff).history.list_applications()
    assert [r["status"] for r in recovered] == ["succeeded", "interrupted"]


def _legacy_attempt(app, number=1):
    import shutil

    package = app.package
    identity = package.state.capture_identity()
    attempt = package.root / f"application_runs/attempt_{number:04d}"
    review = attempt / "input_review"
    review.mkdir(parents=True)
    for rel in set(package.reads) | set(package.writes):
        source = package.readable(rel) if rel in package.reads else package.writable(rel)
        if source.is_file():
            target = review / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    data = json.loads(package.handoff_path.read_text())
    data["source_manifest"] = str(package.root.parent / "manifest.json")
    (review / "manual_correction_input.json").write_bytes(encoded(data))
    (attempt / "consumed_inputs.json").write_bytes(encoded(identity))
    return attempt, identity


def test_legacy_import_reproduces_identities_without_certifying_pdf_success(tmp_path):
    from tools.review_correction.legacy import import_attempt, list_attempts

    app = _application(tmp_path)
    attempt, identity = _legacy_attempt(app)
    # Existence of a PDF is deliberately irrelevant to saved-input import.
    (attempt / "not_a_success.pdf").write_bytes(b"%PDF-invalid")
    assert list_attempts(app.package) == [
        {"id": "attempt_0001", "available": True, "status": "saved_inputs_only"}
    ]
    original = {
        str(p.relative_to(attempt)): p.read_bytes() for p in attempt.rglob("*") if p.is_file()
    }
    with app.package.history.transaction():
        cp = import_attempt(app.package, "attempt_0001")
        assert import_attempt(app.package, "attempt_0001") == cp
    saved = app.package.history.get(cp)
    assert saved["origin"]["original_identity"] == identity
    assert saved["identity"]["corrections_identity"] == identity["corrections_identity"]
    assert app.package.state.snapshot()["package"]["last_successful_result"] is None
    assert original == {
        str(p.relative_to(attempt)): p.read_bytes() for p in attempt.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("changed", ["source", "corrections", "identity"])
def test_legacy_import_rejects_changed_inputs_and_keeps_checkpoints(tmp_path, changed):
    from tools.review_correction.legacy import import_attempt, list_attempts

    app = _application(tmp_path)
    app.package.record_correction(0, "barline_construction", [])
    attempt, _ = _legacy_attempt(app)
    if changed == "source":
        (attempt / "input_review/pages/page_001/source.png").write_bytes(b"changed")
    elif changed == "corrections":
        (attempt / "input_review/corrections/barlines.json").write_bytes(
            encoded({"correction_type": "barline_construction", "items": [{"page": 0, "x": 100}]})
        )
        # Use the declared sink, independent of fixture filename conventions.
        sink = next(
            p
            for rel, p in ReviewPackage(
                attempt / "input_review/manual_correction_input.json"
            ).writes.items()
            if "barline" in rel
        )
        sink.write_bytes(
            encoded({"correction_type": "barline_construction", "items": [{"page": 0, "x": 100}]})
        )
    else:
        data = json.loads((attempt / "consumed_inputs.json").read_text())
        data["source_identity"] = "0" * 64
        (attempt / "consumed_inputs.json").write_bytes(encoded(data))
    before = app.package.history.list()
    assert not list_attempts(app.package)[0]["available"]
    with app.package.history.transaction(), pytest.raises(ValueError):
        import_attempt(app.package, "attempt_0001")
    assert app.package.history.list() == before
