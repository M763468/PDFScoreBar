"""Identity v3: a review's correction state survives moving its job folder (#543)."""

import json
import os
import shutil

import pytest
from test_review_correction_application import _fake_engine
from test_review_correction_server import _handoff

from docker.distribution_job import prepare_local_review
from tools.review_correction import application
from tools.review_correction.application import CorrectionApplication
from tools.review_correction.history import (
    IDENTITY_VERSION,
    canonical_manifest_identity,
    digest,
    encoded,
    recorded_package_file,
)
from tools.review_correction.resume import trusted_numbered_results
from tools.review_correction.server import ReviewPackage

JOB = "job-one"
# A recorded absolute root on this platform (a drive is prepended on Windows).
ENGINE_ROOT = os.path.abspath("/results/job-one/.engine-work")


def _job(tmp_path, where="first"):
    """A prepared local job whose retained manifest references files inside the job."""
    handoff = _handoff(tmp_path / where)
    job = handoff.parent.parent
    payload = json.loads(handoff.read_text())
    payload["source_job_id"] = JOB
    handoff.write_text(json.dumps(payload))
    retained = job / ".engine-retained"
    run = retained / "runs" / JOB
    (run / "inputs/images").mkdir(parents=True)
    (run / "inputs/images/page_001.png").write_bytes(b"retained page image")
    (retained / "input").mkdir()
    (retained / "input/source.pdf").write_bytes(b"%PDF-1.4 source")
    manifest = {
        "run_dir": f"{ENGINE_ROOT}/runs/{JOB}",
        "config": {
            "inputs": {"pdf_path": f"{ENGINE_ROOT}/input/source.pdf"},
            "mmr": {"model_path": "models/mmr/mmr_classifier_best.pth", "threshold": 0.5},
            "steps": {},
            "outputs": {},
        },
        "pages": [
            {
                "image_path": f"{ENGINE_ROOT}/runs/{JOB}/inputs/images/page_001.png",
                "source_reference": None,
            }
        ],
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    prepare_local_review(job)
    return job


def _local_manifest(job):
    return job / ".engine-retained/runs" / JOB / "local_manifest.json"


def _move(job, tmp_path, where="moved/deeper"):
    """Move the whole job folder, then prepare it again as the launcher does on reopen."""
    target = tmp_path / where / job.name
    target.parent.mkdir(parents=True)
    before = _local_manifest(job).read_bytes()
    shutil.move(job, target)
    prepare_local_review(target)
    # The prepared manifest records the new absolute location.
    assert _local_manifest(target).read_bytes() != before
    assert json.loads(_local_manifest(target).read_text())["run_dir"].startswith(str(target))
    return target


def _app(job):
    handoff = job / "review/manual_correction_input.json"
    return CorrectionApplication(ReviewPackage(handoff), handoff)


def _apply(app, monkeypatch):
    monkeypatch.setattr(application, "apply_corrections_and_rerun", _fake_engine)
    app.start()
    app.thread.join(5)
    package = app.package.state.snapshot()["package"]
    assert package["last_application"]["status"] == "succeeded", package
    return package["last_successful_result"]


def _record(app, x):
    app.package.record_correction(0, "barline_construction", [{"page": 0, "op": "add", "x": x}])


def _checkpoint(package):
    with package.history.transaction():
        return package.history.capture()


def test_moved_job_keeps_applied_state_history_and_regeneration(tmp_path, monkeypatch):
    job = _job(tmp_path)
    app = _app(job)
    _record(app, 9)
    applied = _apply(app, monkeypatch)
    assert applied["identity_version"] == IDENTITY_VERSION == 3
    assert applied["final_pdf_package_path"].startswith("application_runs/attempt_0001/")
    checkpoints = app.package.history.list()
    pdf = app.result().read_bytes()

    moved = _move(job, tmp_path)
    reopened = _app(moved)
    package = reopened.package.state.snapshot()["package"]
    assert package["current_result"] == applied
    assert package["counts"]["current"] and not package["counts"]["stale"]
    # The recorded PDF is found inside the moved package, not at its former path.
    assert not os.path.exists(applied["final_pdf"])
    assert reopened.result().read_bytes() == pdf
    assert reopened.result().is_relative_to(moved)
    # The unchanged review reuses its checkpoint; its dependencies resolve in the job.
    assert _checkpoint(reopened.package) == applied["checkpoint_id"]
    assert reopened.package.history.list() == checkpoints

    restored = tmp_path / "restored/review"
    reopened.package.history.materialize(applied["checkpoint_id"], restored)
    retained = json.loads((restored.parent / "retained/manifest.json").read_text())
    assert retained["pages"][0]["image_path"] == str(
        moved / ".engine-retained/runs" / JOB / "inputs/images/page_001.png"
    )
    assert str(job) not in json.dumps(retained)

    # A further save is a real change; regenerating it works in the new location.
    _record(reopened, 12)
    assert reopened.package.state.snapshot()["package"]["counts"]["stale"]
    second = _apply(reopened, monkeypatch)
    assert second["final_pdf"].startswith(str(moved))
    assert reopened.package.state.snapshot()["package"]["current_result"] == second


def test_real_changes_after_a_move_are_still_stale(tmp_path, monkeypatch):
    job = _job(tmp_path)
    app = _app(job)
    applied = _apply(app, monkeypatch)
    moved = _move(job, tmp_path)
    original = moved / ".engine-retained/runs" / JOB / "manifest.json"
    payload = json.loads(original.read_text())
    payload["config"]["mmr"]["threshold"] = 0.6
    original.write_text(json.dumps(payload))
    prepare_local_review(moved)
    package = _app(moved).package.state.snapshot()["package"]
    assert package["last_successful_result"] == applied
    assert package["current_result"] is None
    assert package["counts"]["stale"]


def test_changed_retained_dependency_after_a_move_blocks_reuse(tmp_path, monkeypatch):
    job = _job(tmp_path)
    app = _app(job)
    checkpoint = _checkpoint(app.package)
    moved = _move(job, tmp_path)
    image = moved / ".engine-retained/runs" / JOB / "inputs/images/page_001.png"
    image.write_bytes(b"changed image")
    package = _app(moved).package
    with pytest.raises(ValueError, match="dependency changed"):
        package.history.validate_dependencies(checkpoint)


def test_retained_dependency_symlink_out_of_the_job_is_rejected(tmp_path):
    job = _job(tmp_path)
    checkpoint = _checkpoint(_app(job).package)
    moved = _move(job, tmp_path)
    image = moved / ".engine-retained/runs" / JOB / "inputs/images/page_001.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(image.read_bytes())
    image.unlink()
    image.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its job"):
        _app(moved).package.history.validate_dependencies(checkpoint)


def test_dependencies_are_not_taken_from_the_former_location_or_another_job(tmp_path):
    job = _job(tmp_path)
    checkpoint = _checkpoint(_app(job).package)
    # A copy leaves the former job in place; the copy must use its own files.
    copy = tmp_path / "copy" / job.name
    shutil.copytree(job, copy)
    image = copy / ".engine-retained/runs" / JOB / "inputs/images/page_001.png"
    image.write_bytes(b"different")
    with pytest.raises(ValueError, match="dependency changed"):
        _app(copy).package.history.validate_dependencies(checkpoint)
    # A review placed in a job that does not retain this run never resolves into it.
    other = tmp_path / "other" / job.name
    shutil.copytree(job, other)
    shutil.move(other / ".engine-retained/runs" / JOB, other / ".engine-retained/runs/job-two")
    shutil.rmtree(job)
    with pytest.raises(ValueError, match="dependency changed or is unavailable"):
        _app(other).package.history.validate_dependencies(checkpoint)


def _write_checkpoint(package, value):
    package.history._prepare()
    data = encoded(value)
    checkpoint = "cp_" + digest(data)
    directory = package.history.root / "checkpoints" / checkpoint
    directory.mkdir()
    (directory / "checkpoint.json").write_bytes(data)
    return checkpoint


def _legacy_result(job, version):
    """A result and checkpoint exactly as identity v1/v2 recorded them, before a move."""
    package = _app(job).package
    identity = package.state.capture_identity(version=version)
    history = package.history
    history._prepare()
    files = {
        rel: history.put(path.read_bytes()) if path.is_file() else None
        for rel in sorted(set(package.reads) | set(package.writes))
        for path in [package.readable(rel) if rel in package.reads else package.writable(rel)]
    }
    files["manual_correction_input.json"] = history.put(package.handoff_path.read_bytes())
    checkpoint = _write_checkpoint(
        package,
        {
            "schema_version": version,
            "created_at": "2026-01-01T00:00:00.000000+00:00",
            "label": "",
            "identity": identity,
            "files": files,
            "source_context": history._source_context(package),
        },
    )
    state = package.root / "corrections/.correction_state.json"
    state.parent.mkdir(exist_ok=True)
    result = {**identity, "checkpoint_id": checkpoint, "result_identity": f"v{version}"}
    state.write_text(json.dumps({"schema_version": 1, "last_successful_result": result}))
    return result, checkpoint


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_result_survives_a_move_through_its_retained_manifest(tmp_path, version):
    job = _job(tmp_path)
    result, checkpoint = _legacy_result(job, version)
    stored = (job / "review/corrections/.correction_state.json").read_bytes()
    moved = _move(job, tmp_path)
    package = _app(moved).package
    assert package.state.capture_identity(version=version)["identity"] != result["identity"]
    snapshot = package.state.snapshot()["package"]
    assert snapshot["current_result"] == result
    # The stored record is matched, never rewritten, and its checkpoint is reused.
    assert (moved / "review/corrections/.correction_state.json").read_bytes() == stored
    assert _checkpoint(package) == checkpoint


@pytest.mark.parametrize("version", [1, 2])
def test_reused_legacy_checkpoint_after_a_move_can_be_applied(tmp_path, monkeypatch, version):
    job = _job(tmp_path)
    _, checkpoint = _legacy_result(job, version)
    moved = _move(job, tmp_path)
    app = _app(moved)
    applied = _apply(app, monkeypatch)
    assert applied["checkpoint_id"] == checkpoint
    assert applied["identity_version"] == IDENTITY_VERSION
    assert app.package.history.list_applications()[0]["checkpoint_id"] == checkpoint
    assert app.package.state.snapshot()["package"]["current_result"] == applied
    assert app.result().is_relative_to(moved)


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_result_without_a_relocation_proof_is_stale(tmp_path, version):
    job = _job(tmp_path)
    result, checkpoint = _legacy_result(job, version)
    shutil.rmtree(job / "review/history/checkpoints" / checkpoint)
    moved = _move(job, tmp_path)
    snapshot = _app(moved).package.state.snapshot()["package"]
    assert snapshot["last_successful_result"] == result
    assert snapshot["current_result"] is None


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_result_is_stale_when_more_than_the_location_changed(tmp_path, version):
    job = _job(tmp_path)
    _legacy_result(job, version)
    moved = _move(job, tmp_path)
    original = moved / ".engine-retained/runs" / JOB / "manifest.json"
    payload = json.loads(original.read_text())
    payload["config"]["mmr"]["model_path"] = "models/mmr/other.pth"
    original.write_text(json.dumps(payload))
    prepare_local_review(moved)
    assert _app(moved).package.state.snapshot()["package"]["current_result"] is None


def _manifest(root, job=JOB, **config):
    root = os.path.abspath(root)
    return encoded(
        {
            "run_dir": f"{root}/.engine-retained/runs/{job}",
            "config": {"pdf": f"{root}/.engine-retained/input/source.pdf", **config},
            "pages": [{"image": f"{root}/.engine-retained/runs/{job}/page.png"}],
        }
    )


def test_canonical_manifest_identity_ignores_only_the_job_location():
    first = canonical_manifest_identity(_manifest("/a/job"))
    assert canonical_manifest_identity(_manifest("/elsewhere/mounted/job")) == first
    assert canonical_manifest_identity(_manifest("/a/job", threshold=1)) != first
    assert canonical_manifest_identity(_manifest("/a/job", job="job-two")) != first
    assert canonical_manifest_identity(_manifest("/a/job", model="/a/other/model")) != (
        canonical_manifest_identity(_manifest("/a/job", model="/a/another/model"))
    )
    # Non-retained layouts, escaping references and invalid JSON keep their exact bytes.
    plain = encoded({"run_dir": "/a/runs/job-one", "pages": []})
    assert canonical_manifest_identity(plain) == canonical_manifest_identity(plain)
    assert canonical_manifest_identity(plain) != canonical_manifest_identity(
        encoded({"run_dir": "/b/runs/job-one", "pages": []})
    )
    escaping = json.loads(_manifest("/a/job"))
    escaping["config"]["pdf"] = os.path.abspath("/a/job") + "/../outside.pdf"
    moved = json.loads(_manifest("/b/job"))
    moved["config"]["pdf"] = os.path.abspath("/b/job") + "/../outside.pdf"
    assert canonical_manifest_identity(encoded(escaping)) != canonical_manifest_identity(
        encoded(moved)
    )
    assert canonical_manifest_identity(b"not json") != canonical_manifest_identity(b"not  json")


def test_recorded_result_files_resolve_only_inside_the_package(tmp_path):
    root = tmp_path / "review"
    target = root / "application_runs/attempt_0001/corrected/final/a.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF")
    legacy = {"final_pdf": "/old/place/review/application_runs/attempt_0001/corrected/final/a.pdf"}
    assert recorded_package_file(root, legacy, "final_pdf") == target
    current = {"final_pdf_package_path": "application_runs/attempt_0001/corrected/final/a.pdf"}
    assert recorded_package_file(root, current, "final_pdf") == target
    for record in (
        {"final_pdf": "/old/place/review/final/a.pdf"},
        {"final_pdf_package_path": "final/a.pdf"},
        {"final_pdf_package_path": "application_runs/../../escape.pdf"},
        {"final_pdf": None},
    ):
        with pytest.raises(ValueError):
            recorded_package_file(root, record, "final_pdf")


def test_trusted_numbered_results_follow_a_moved_package(tmp_path):
    root = tmp_path / "review"
    final = root / "application_runs/attempt_0001/corrected/final"
    final.mkdir(parents=True)
    (final / "a.pdf").write_bytes(b"%PDF numbered")
    (final / "a.layer.json").write_text("{}")
    old = "/old/place/review/application_runs/attempt_0001/corrected/final"
    record = {
        "status": "succeeded",
        "result": {
            "final_pdf": f"{old}/a.pdf",
            "final_pdf_sha256": digest(b"%PDF numbered"),
            "number_layer_sidecar": f"{old}/a.layer.json",
            "number_layer_sidecar_sha256": digest(b"{}"),
        },
    }
    (root / "history/applications").mkdir(parents=True)
    (root / "history/applications/attempt_0001.json").write_text(json.dumps(record))

    class Package:
        pass

    package = Package()
    package.root = root
    assert list(trusted_numbered_results(package)) == [(final / "a.pdf", final / "a.layer.json")]
    (final / "a.pdf").write_bytes(b"%PDF changed")
    assert list(trusted_numbered_results(package)) == []
