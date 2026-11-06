"""Versioned review identity: output_name is metadata, v1 records stay readable as written."""

import hashlib
import json

import fitz
import pytest
from test_review_correction_application import _application, _fake_engine
from test_review_correction_history import (
    _checkpoint,
    _pdf_package,
    _prepared_legacy_job,
    _reopen_with_recovered_name,
    _set_job_output_name,
)
from test_review_correction_state import _recorded, _state

from src.pipeline.review.final_output import _derive_output_name
from tools.review_correction import application
from tools.review_correction.history import digest, encoded
from tools.review_correction.legacy import import_attempt, list_attempts
from tools.review_correction.resume import create_session
from tools.review_correction.server import ReviewPackage
from tools.review_correction.state import CorrectionState

HANDOFF = "manual_correction_input.json"


def _rewrite(handoff, **fields):
    payload = json.loads(handoff.read_text())
    payload.update(fields)
    handoff.write_text(json.dumps(payload))


def _write_checkpoint(package, value):
    """Store a manifest the way any earlier writer did: ID is its content hash."""
    package.history._prepare()
    data = encoded(value)
    checkpoint = "cp_" + digest(data)
    directory = package.history.root / "checkpoints" / checkpoint
    directory.mkdir()
    (directory / "checkpoint.json").write_bytes(data)
    return checkpoint


def _schema1_checkpoint(package, label="existing"):
    """A checkpoint exactly as schema 1 wrote it, independent of the current writer."""
    history = package.history
    history._prepare()
    files = {
        rel: history.put(path.read_bytes()) if path.is_file() else None
        for rel in sorted(set(package.reads) | set(package.writes))
        for path in [package.readable(rel) if rel in package.reads else package.writable(rel)]
    }
    files[HANDOFF] = history.put(package.handoff_path.read_bytes())
    return _write_checkpoint(
        package,
        {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00.000000+00:00",
            "label": label,
            "identity": package.state.capture_identity(version=1),
            "files": files,
            "source_context": history._source_context(package),
        },
    )


def _apply(app, monkeypatch):
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    assert app.package.state.snapshot()["package"]["last_application"]["status"] == "succeeded"


def _reopen_state(root, state):
    return CorrectionState(root, state.pages, root / HANDOFF)


def _tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_identity_v1_stays_byte_reproducible(tmp_path):
    state, root = _state(tmp_path)
    (root / "manual_correction_input.json").write_text('{"output_name": "A",  "schema_version": 1}')

    def sha(name):
        return hashlib.sha256((root / name).read_bytes()).hexdigest()

    def canonical(value):
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode()).hexdigest()

    source = canonical(
        {
            "source.png": sha("source.png"),
            "numbering.json": sha("numbering.json"),
            "manual_correction_input.json": sha("manual_correction_input.json"),
        }
    )
    corrections = canonical(
        {
            "0:mmr_measure_span": {"files": [{"exists": False, "content": None}]},
            "0:measure_construction": {"files": [{"exists": False, "content": None}]},
        }
    )
    assert state.capture_identity(version=1) == {
        "source_identity": source,
        "corrections_identity": corrections,
        "identity": canonical({"source": source, "corrections": corrections}),
    }


@pytest.mark.parametrize("name", ["Named", "Other", "", "   ", ".", "../../escape", 123, None])
def test_output_name_alone_does_not_change_identity_v2(tmp_path, name):
    state, root = _state(tmp_path)
    handoff = root / HANDOFF
    before = state.capture_identity()
    before_v1 = state.capture_identity(version=1)
    assert before["identity_version"] == 2
    _rewrite(handoff, output_name=name)
    assert state.capture_identity() == before
    assert state.capture_identity(version=1) != before_v1
    # Removing the name is the same case, and so is a change in serialization alone.
    payload = json.loads(handoff.read_text())
    payload.pop("output_name")
    handoff.write_text(json.dumps(payload, indent=4))
    assert state.capture_identity() == before


@pytest.mark.parametrize(
    "change",
    ["handoff_body", "page_order", "nested_name", "resume", "not_json", "source", "correction"],
)
def test_identity_v2_changes_with_everything_except_output_name(tmp_path, change):
    state, root = _state(tmp_path)
    handoff = root / HANDOFF
    handoff.write_text(json.dumps({"schema_version": 1, "pages": ["a", "b"], "x": {}}))
    # Keep the source context resolvable for the resume case.
    (root / "resume.pdf").write_bytes(b"%PDF-resume")
    before = state.capture_identity()
    if change == "handoff_body":
        _rewrite(handoff, source_title="Changed")
    elif change == "page_order":
        _rewrite(handoff, pages=["b", "a"])
    elif change == "nested_name":
        _rewrite(handoff, x={"output_name": "Only top-level is metadata"})
    elif change == "resume":
        _rewrite(handoff, resume={"input_pdf": "resume.pdf"})
    elif change == "not_json":
        handoff.write_bytes(b"not json")
    elif change == "source":
        (root / "source.png").write_bytes(b"source-b")
    else:
        _recorded(root / "corrections/mmr.json", "mmr_measure_span", [{"page": 0}])
    after = state.capture_identity()
    assert after["identity"] != before["identity"]
    changed_key = "corrections_identity" if change == "correction" else "source_identity"
    assert after[changed_key] != before[changed_key]


def test_identity_v2_changes_with_source_manifest(tmp_path):
    app = _application(tmp_path)
    before = app.package.state.capture_identity()
    manifest = app.package.root.parent / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["config"]["inputs"]["changed"] = True
    manifest.write_bytes(encoded(payload))
    assert app.package.state.capture_identity()["source_identity"] != before["source_identity"]


def test_v2_result_stays_current_across_names_but_not_real_changes(tmp_path, monkeypatch):
    app = _application(tmp_path)
    _apply(app, monkeypatch)
    state = app.package.state
    applied = state.snapshot()["package"]["last_successful_result"]
    assert applied["identity_version"] == 2
    _rewrite(app.handoff, output_name="Renamed")
    package = state.snapshot()["package"]
    assert package["current_result"] == applied
    assert package["counts"]["current"] and not package["counts"]["stale"]
    assert app.result().is_file()
    # A restart reads the same recorded result under the same rule.
    assert ReviewPackage(app.handoff).state.snapshot()["package"]["current_result"] == applied
    app.package.record_correction(0, "barline_construction", [{"page": 0, "op": "add", "x": 9}])
    package = state.snapshot()["package"]
    assert package["current_result"] is None
    assert package["counts"]["stale"]


def test_v1_result_matches_only_byte_identical_handoff(tmp_path):
    state, root = _state(tmp_path)
    (root / "corrections").mkdir()
    (root / "corrections/.correction_state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "last_successful_result": {
                    **state.capture_identity(version=1),
                    "result_identity": "old",
                },
            }
        )
    )
    reopened = _reopen_state(root, state)
    assert reopened.snapshot()["package"]["current_result"]["result_identity"] == "old"
    _rewrite(root / HANDOFF, output_name="Renamed")
    package = reopened.snapshot()["package"]
    assert package["current_result"] is None
    assert package["last_successful_result"]["result_identity"] == "old"
    assert package["counts"]["stale"]


@pytest.mark.parametrize(
    "recorded",
    [
        {"identity_version": 3, "identity": "x"},
        {"identity_version": "2", "identity": "x"},
        {"identity_version": None, "identity": "x"},
        {
            "identity_version": 2,
            "identity": "x",
            "source_identity": "s",
            "corrections_identity": "c",
        },
    ],
)
def test_unknown_or_inconsistent_result_identity_is_rejected(tmp_path, recorded):
    state, root = _state(tmp_path)
    (root / "corrections").mkdir()
    (root / "corrections/.correction_state.json").write_text(
        json.dumps({"schema_version": 1, "last_successful_result": recorded})
    )
    with pytest.raises(ValueError, match="identity"):
        _reopen_state(root, state)


def test_schema1_checkpoint_stays_usable_and_unchanged(tmp_path):
    package, annotated = _pdf_package(tmp_path)
    existing = _schema1_checkpoint(package)
    before = _tree(package.history.root / "checkpoints" / existing)
    blobs = _tree(package.history.root / "blobs")

    restarted = ReviewPackage(package.handoff_path)
    assert restarted.history.get(existing)["schema_version"] == 1
    assert [item["id"] for item in restarted.history.list()] == [existing]
    assert restarted.history.list()[0]["can_resume_pdf"] is True
    # The unchanged package reuses it rather than duplicating it in schema 2.
    assert _checkpoint(restarted) == existing
    restored = tmp_path / "restored/review"
    restarted.history.materialize(existing, restored)
    assert (
        ReviewPackage(restored / HANDOFF).state.capture_identity()["corrections_identity"]
        == (restarted.history.get(existing)["identity"]["corrections_identity"])
    )
    session = create_session(restarted, existing, annotated)
    resumed = json.loads(
        (
            restarted.root / f"resumed_sessions/{session}/review/manual_correction_input.json"
        ).read_text()
    )
    assert resumed["resume"]["checkpoint_id"] == existing
    assert "identity_version" not in resumed["resume"]["source_identity"]
    assert _tree(restarted.history.root / "checkpoints" / existing) == before
    assert blobs.items() <= _tree(restarted.history.root / "blobs").items()


def test_v1_and_v2_checkpoints_coexist_with_explicit_reuse_rule(tmp_path):
    package, _ = _pdf_package(tmp_path)
    existing = _schema1_checkpoint(package)
    stored = _tree(package.history.root / "checkpoints" / existing)

    # A v1 record cannot be separated from its name: one new v2 checkpoint, then no more.
    _set_job_output_name(package.handoff_path, "Renamed")
    package = ReviewPackage(package.handoff_path)
    upgraded = _checkpoint(package)
    assert upgraded != existing
    value = package.history.get(upgraded)
    assert value["schema_version"] == 2
    assert value["identity"]["identity_version"] == 2
    assert (
        value["identity"]["corrections_identity"]
        == (package.history.get(existing)["identity"]["corrections_identity"])
    )
    _set_job_output_name(package.handoff_path, "Renamed again")
    assert _checkpoint(package) == upgraded
    _set_job_output_name(package.handoff_path, None)
    assert _checkpoint(package) == upgraded
    assert {item["id"] for item in package.history.list()} == {existing, upgraded}
    assert _tree(package.history.root / "checkpoints" / existing) == stored

    # Real changes are still new checkpoints under the current rule.
    package.record_correction(0, "barline_construction", [{"page": 0, "op": "add", "x": 9}])
    latest = package.history.list()[-1]["id"]
    assert latest not in {existing, upgraded}
    assert _checkpoint(package) == latest


def test_checkpoint_keeps_complete_handoff_and_reuse_keeps_its_name(tmp_path):
    package, annotated = _pdf_package(tmp_path)
    _set_job_output_name(package.handoff_path, "First")
    first = _checkpoint(package)
    ref = package.history.get(first)["files"][HANDOFF]
    assert json.loads(package.history.blob(ref))["output_name"] == "First"

    _set_job_output_name(package.handoff_path, "Second")
    assert _checkpoint(package) == first
    assert json.loads(package.history.blob(ref))["output_name"] == "First"
    session = create_session(package, first, annotated)
    saved = package.root / f"resumed_sessions/{session}/review/{HANDOFF}"
    assert _derive_output_name(None, json.loads(saved.read_text())) == "First"

    # An explicit save never reuses a checkpoint, so it retains the changed name.
    with package.history.transaction():
        second = package.history.capture(label="named", force=True)
    assert second != first
    session = create_session(package, second, annotated)
    saved = package.root / f"resumed_sessions/{session}/review/{HANDOFF}"
    assert _derive_output_name(None, json.loads(saved.read_text())) == "Second"


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda v: v.update(schema_version=3), "Unsupported checkpoint schema"),
        (lambda v: v.update(schema_version="2"), "Unsupported checkpoint schema"),
        (lambda v: v["identity"].update(identity_version=3), "Unsupported identity version"),
        (lambda v: v["identity"].update(identity="0" * 64), "inconsistent"),
        (lambda v: v["identity"].pop("identity_version"), "does not match its schema"),
        (lambda v: v.update(schema_version=1), "does not match its schema"),
        (lambda v: v["files"].pop(HANDOFF), "complete handoff"),
    ],
)
def test_invalid_checkpoint_formats_fail_closed_even_with_a_valid_id(tmp_path, tamper, message):
    package, _ = _pdf_package(tmp_path)
    value = package.history.get(_checkpoint(package))
    tamper(value)
    forged = _write_checkpoint(package, value)
    with pytest.raises(ValueError, match=message):
        package.history.get(forged)
    with pytest.raises(ValueError, match=message):
        package.history.list()


@pytest.mark.parametrize("target", ["manifest", "blob"])
def test_changed_stored_v2_checkpoint_is_rejected(tmp_path, target):
    package, _ = _pdf_package(tmp_path)
    checkpoint = _checkpoint(package)
    if target == "manifest":
        path = package.history.root / "checkpoints" / checkpoint / "checkpoint.json"
        value = json.loads(path.read_text())
        value["label"] = "changed"
        path.write_bytes(encoded(value))
    else:
        ref = package.history.get(checkpoint)["files"][HANDOFF]
        (package.history.root / "blobs" / ref["sha256"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        package.history.get(checkpoint)


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (None, "Added", "Added"),
        ("First", "Second", "Second"),
        ("First", None, "corrected"),
    ],
)
def test_apply_reuses_checkpoint_but_uses_the_current_job_name(
    tmp_path, monkeypatch, first, second, expected
):
    app = _application(tmp_path)
    _set_job_output_name(app.handoff, first)
    checkpoint = _checkpoint(app.package)
    _set_job_output_name(app.handoff, second)
    _apply(app, monkeypatch)
    assert [item["id"] for item in app.package.history.list()] == [checkpoint]
    assert app.package.history.list_applications()[0]["checkpoint_id"] == checkpoint
    assert app.result().name == f"{expected}_score_numbered.pdf"
    assert app.package.state.snapshot()["package"]["current_result"] is not None
    retained = app.package.history.get(checkpoint)["files"][HANDOFF]
    assert json.loads(app.package.history.blob(retained)).get("output_name") == first


def test_apply_on_an_existing_schema1_checkpoint_succeeds(tmp_path, monkeypatch):
    app = _application(tmp_path)
    existing = _schema1_checkpoint(app.package)
    _apply(app, monkeypatch)
    record = app.package.history.list_applications()[0]
    assert record["checkpoint_id"] == existing
    assert record["identity"]["identity_version"] == 2
    assert app.package.state.snapshot()["package"]["current_result"] is not None
    # A saved post-checkpoint attempt is still not treated as a legacy attempt.
    assert list_attempts(app.package) == []


def test_recovered_job_name_does_not_stale_a_v2_result_or_add_a_checkpoint(tmp_path, monkeypatch):
    handoff, job, _, _ = _prepared_legacy_job(tmp_path)
    app = application.CorrectionApplication(ReviewPackage(handoff), handoff)
    _apply(app, monkeypatch)
    result = app.package.state.snapshot()["package"]["last_successful_result"]
    checkpoints = app.package.history.list()
    package = _reopen_with_recovered_name(handoff, job)
    assert package.state.snapshot()["package"]["current_result"] == result
    assert _checkpoint(package) == result["checkpoint_id"]
    assert package.history.list() == checkpoints


def test_legacy_import_keeps_v1_origin_and_writes_a_v2_checkpoint(tmp_path):
    handoff, job, attempt, identity = _prepared_legacy_job(tmp_path, "Saved")
    assert "identity_version" not in identity
    package = ReviewPackage(handoff)
    saved = _tree(attempt)
    with package.history.transaction():
        checkpoint = import_attempt(package, attempt.name)
    value = package.history.get(checkpoint)
    assert value["schema_version"] == 2
    assert value["identity"]["identity_version"] == 2
    assert value["origin"]["original_identity"] == identity
    assert value["identity"]["corrections_identity"] == identity["corrections_identity"]
    assert package.state.snapshot()["package"]["last_successful_result"] is None
    assert _tree(attempt) == saved
    # Import keeps the attempt's name and returns the same checkpoint after a job rename.
    _set_job_output_name(handoff, "Changed")
    package = ReviewPackage(handoff)
    with package.history.transaction():
        assert import_attempt(package, attempt.name) == checkpoint
    assert json.loads(package.history.blob(value["files"][HANDOFF]))["output_name"] == "Saved"


def test_legacy_attempt_recording_a_v2_identity_is_not_importable(tmp_path):
    handoff, _, attempt, _ = _prepared_legacy_job(tmp_path)
    package = ReviewPackage(handoff)
    # The adapter reproduces only the byte-based rule those attempts really recorded.
    consumed = attempt / "consumed_inputs.json"
    consumed.write_bytes(encoded(package.state.capture_identity()))
    entry = list_attempts(package)[0]
    assert entry["available"] is False
    assert "inconsistent" in entry["error"]


def test_resume_pdf_checks_are_not_relaxed_for_either_schema(tmp_path):
    package, annotated = _pdf_package(tmp_path)
    schema1 = _schema1_checkpoint(package)
    _set_job_output_name(package.handoff_path, "Renamed")
    schema2 = _checkpoint(package)
    assert package.history.get(schema2)["schema_version"] == 2
    with fitz.open() as doc:
        doc.new_page(width=200, height=260).draw_circle((100, 100), 40)
        unknown = doc.tobytes()
    for checkpoint in (schema1, schema2):
        with pytest.raises(ValueError, match="does not match"):
            create_session(package, checkpoint, unknown)
        assert create_session(package, checkpoint, annotated)
