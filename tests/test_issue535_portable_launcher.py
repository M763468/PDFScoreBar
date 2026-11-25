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
    at the old absolute path in the platform's native separators."""

    job = tmp_path / "new" / JOB
    retained = job / ".engine-retained" / "runs" / JOB / "intermediate" / "page_001"
    retained.mkdir(parents=True)
    (job / "review").mkdir()
    dependency = retained / "numbering_base.json"
    dependency.write_bytes(b'{"pages": []}')
    old_root = str(tmp_path / "old" / JOB)
    run_dir = os.path.join(old_root, ".engine-retained", "runs", JOB)
    recorded = os.path.join(run_dir, "intermediate", "page_001", "numbering_base.json")
    return job, dependency, recorded, {"run_dir": run_dir}


def _store(job: Path, recorded: str, expected: str, manifest: dict):
    from types import SimpleNamespace

    from tools.review_correction.history import CheckpointStore

    store = CheckpointStore(SimpleNamespace(root=job / "review"))
    context = {"manifest": manifest, "dependencies": {recorded: expected}}
    store.get = lambda _id: {"source_context": context}
    return store


def test_checkpoint_dependencies_follow_a_moved_job(tmp_path: Path) -> None:
    from tools.review_correction.history import digest

    job, dependency, recorded, manifest = _moved_job(tmp_path)
    store = _store(job, recorded, digest(dependency.read_bytes()), manifest)
    context = store.validate_dependencies("cp")["source_context"]
    rebound = store._rebinder(context)({"pages": [{"numbering": recorded}]})
    assert rebound == {"pages": [{"numbering": str(dependency)}]}


def test_moved_checkpoint_dependencies_still_need_identical_bytes(tmp_path: Path) -> None:
    job, _dependency, recorded, manifest = _moved_job(tmp_path)
    store = _store(job, recorded, "0" * 64, manifest)
    with pytest.raises(ValueError, match="Retained source dependency"):
        store.validate_dependencies("cp")


def test_rebind_rejects_a_reference_that_escapes_the_job(tmp_path: Path) -> None:
    from tools.review_correction.history import rebind_job_paths

    job, _dependency, _recorded, manifest = _moved_job(tmp_path)
    old_root = str(tmp_path / "old" / JOB)
    escape = os.path.join(old_root, ".engine-retained", "..", "..", "secret.json")
    with pytest.raises(ValueError):
        rebind_job_paths(escape, old_root, job)
    other = os.path.join(str(tmp_path / "old" / "job-ffffffffffff"), "x.json")
    assert rebind_job_paths(other, old_root, job) == other


@pytest.mark.parametrize("server_name", ["LocalHTTPServer", "LocalThreadingHTTPServer"])
def test_review_and_browser_servers_refuse_a_port_in_use(server_name: str) -> None:
    from http.server import BaseHTTPRequestHandler

    from tools.review_correction import server as review_server

    server_class = getattr(review_server, server_name)
    with server_class(("127.0.0.1", 0), BaseHTTPRequestHandler) as first:
        # On Windows SO_REUSEADDR used to let a second server share the port (#535).
        with pytest.raises(OSError):
            server_class(("127.0.0.1", first.server_port), BaseHTTPRequestHandler)


def test_rebind_covers_the_retained_detector_output(tmp_path: Path) -> None:
    from tools.review_correction.history import rebind_job_paths

    # Windows retains detector output under .engine-retained/h/<job> (short work root).
    job = tmp_path / "new" / JOB
    job.mkdir(parents=True)
    old_root = os.path.join(str(tmp_path / "old"), JOB)
    old = os.path.join(old_root, ".engine-retained", "h", JOB, "mask.png")
    assert rebind_job_paths(old, old_root, job) == str(
        job / ".engine-retained" / "h" / JOB / "mask.png"
    )


# --- #551: the portable payload is the main application plus a Windows allowlist -----

import copy  # noqa: E402
import fnmatch  # noqa: E402
import hashlib  # noqa: E402
import subprocess  # noqa: E402

from tools.windows_portable import build_portable  # noqa: E402

payload = build_portable.payload  # the builder's own module objects
portable_manifest = sys.modules["manifest"]
REPO = Path(__file__).resolve().parents[1]
OVERLAY = {"PDFScoreBar.cmd", "launcher/launcher.py", "launcher/manifest.py"}


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True).stdout


@pytest.fixture(scope="module")
def head() -> str:
    return _git("rev-parse", "HEAD").decode().strip()


@pytest.fixture(scope="module")
def snap(head: str):
    return payload.snapshot(REPO, head)


def _tracked(commit: str) -> list[str]:
    return [p.decode() for p in _git("ls-tree", "-rz", "--name-only", commit).split(b"\0") if p]


def test_application_is_the_main_candidate_selection(snap, head: str) -> None:
    import release_candidate  # the main release generator, as payload imports it

    content, provenance = release_candidate.snapshot(REPO, head, head)
    main_files = {path for path in content if path != release_candidate.PROVENANCE}
    assert set(snap.selected) == main_files
    assert len(snap.selected) >= 130  # not merely smaller: every selected file is present
    for path in snap.selected:
        assert snap.app[path] == content[path], path
        assert snap.app[path] == _git("cat-file", "blob", f"{head}:{path}"), path
    shipped = json.loads(snap.app[payload.PROVENANCE])
    assert shipped == {
        "schema_version": 1,
        "source_commit": head,
        "source_branch": "detached",
        "source_dirty": False,
        "files": provenance["files"],
    }
    record = snap.application_record()
    assert record["files"] == provenance["files"]
    assert record["manifest_sha256"] == provenance["release"]["manifest_sha256"]
    assert record["selection_sections"] == list(payload.SECTIONS)


def test_staged_payload_is_app_plus_the_allowlist_only(snap, tmp_path: Path) -> None:
    payload.stage(snap, tmp_path)
    staged = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    app = {f"app/{path}" for path in snap.app}
    assert staged == app | OVERLAY
    assert payload.check_tree(tmp_path / "app") == []
    # The launcher is shipped outside app/; the builder, tests and docs are not shipped.
    for path in snap.spec["build_inputs"]:
        assert f"app/{path}" not in staged and path not in staged
    assert not any(p.startswith(("app/tools/windows_portable/", "app/tests/")) for p in staged)
    cmd = (tmp_path / "PDFScoreBar.cmd").read_bytes()
    assert cmd.endswith(b"\r\n") and b"\n" not in cmd.replace(b"\r\n", b"")
    assert b"launcher\\launcher.py" in cmd


def test_forbidden_patterns_guard_real_development_and_not_licensed_files(snap, head) -> None:
    tracked = _tracked(head)
    patterns = snap.spec["forbidden_payload_patterns"]
    for entry in patterns:
        if entry["category"] == "not_licensed":
            assert fnmatch.filter(tracked, entry["pattern"]), entry["pattern"]
    # The former builder shipped `git archive`: the guard rejects that surface.
    with pytest.raises(ValueError) as error:
        payload.validate_spec(snap.spec, set(tracked), set(tracked))
    for expected in ("data/evaluation2/", "tests/", "tools/issue522/evidence/", ".github/"):
        assert expected in str(error.value)
    for path in snap.app:
        hits = portable_manifest.forbidden_matches(path, patterns)
        assert not hits or path in snap.spec["rights_pending_required"], (path, hits)


def test_overlay_entries_are_windows_only_and_explained(snap) -> None:
    sources = {entry["source"] for entry in snap.overlay_records}
    assert sources == {
        "tools/windows_portable/launcher.py",
        "tools/windows_portable/manifest.py",
        "tools/windows_portable/PDFScoreBar.cmd",
    }
    assert {entry["path"] for entry in snap.overlay_records} == OVERLAY
    assert all(entry["reason"] for entry in snap.overlay_records)
    for section in ("common_inactive_on_windows", "rights_pending_required"):
        assert set(snap.spec[section]) <= set(snap.selected)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda s: s["source_files"][0].update(source="tools/browser_jobs/jobs.py"),
            "overlay source",
        ),
        (lambda s: s["source_files"][0].update(path="app/tools/x.py"), "destination"),
        (lambda s: s["source_files"][1].update(path="launcher/launcher.py"), "duplicate"),
        (lambda s: s["source_files"][0].update(reason=""), "reason"),
        (
            lambda s: s["source_files"][0].update(source="tools/windows_portable/payload.py"),
            "overlay source",
        ),
        (
            lambda s: s["generated"].append({"path": "tests", "reason": "x", "verified_by": "x"}),
            "Generated",
        ),
        (
            lambda s: s["build_inputs"].pop("tools/windows_portable/requirements-cu126.txt"),
            "not recorded",
        ),
        (lambda s: s["common_inactive_on_windows"].update({"tests/conftest.py": "x"}), "selected"),
        (lambda s: s["application"].update(manifest="docs/OTHER.json"), "application contract"),
    ],
)
def test_overlay_spec_fails_closed(snap, head, mutate, message: str) -> None:
    spec = copy.deepcopy(snap.spec)
    mutate(spec)
    with pytest.raises(ValueError, match=message):
        payload.validate_spec(spec, set(snap.selected), set(_tracked(head)))


def test_required_runtime_references_are_shipped(snap) -> None:
    assert payload.runtime_reference_problems(snap) == []
    for missing, expected in [
        ("models/mmr/mmr_classifier_best.pth", "configs/dense_full_pipeline.yaml"),
        ("models/sr_x4/pdfscorebar_sr_x4_issue533_s1r.pth", "models/sr_x4/manifest.json"),
        ("docker/distribution_job.py", "docker.distribution_job"),
        ("src/pipeline/detection/maintained_homr_worker.py", "maintained_homr_worker.py"),
        ("tools/browser_jobs/server.py", "tools.browser_jobs.server"),
        ("docker/init_homr_segnet.py", "Build-time application script"),
    ]:
        broken = copy.copy(snap)
        broken.app = {k: v for k, v in snap.app.items() if k != missing}
        problems = payload.runtime_reference_problems(broken)
        assert any(expected in problem for problem in problems), (missing, problems)


def test_snapshot_needs_a_frozen_commit_and_a_pinned_builder(snap, tmp_path, monkeypatch) -> None:
    with pytest.raises(ValueError, match="40-character"):
        payload.snapshot(REPO, "HEAD")
    hashes = payload.check_running_builder(snap)
    assert hashes == {path: hashlib.sha256(snap.builder[path]).hexdigest() for path in hashes}
    crlf = tmp_path / "payload.py"
    crlf.write_bytes(snap.builder["tools/windows_portable/payload.py"].replace(b"\n", b"\r\n"))
    modules = dict(payload.BUILDER_MODULES, **{"tools/windows_portable/payload.py": crlf})
    monkeypatch.setattr(payload, "BUILDER_MODULES", modules)
    payload.check_running_builder(snap)  # an autocrlf checkout is the same builder
    crlf.write_bytes(crlf.read_bytes() + b"# local edit\r\n")
    with pytest.raises(ValueError, match="differs from the pinned commit"):
        payload.check_running_builder(snap)


def _portable(snap, root: Path) -> Path:
    """A folder with the real app/launcher payload and stand-in runtime/asset bytes."""

    payload.stage(snap, root)
    (root / "python" / "Lib" / "site-packages").mkdir(parents=True)
    (root / "python" / "python.exe").write_bytes(b"stand-in interpreter")
    assets = []
    for asset in json.loads(snap.inputs[payload.ASSETS])["assets"]:
        target = root / asset["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(asset["path"].encode())
        assets.append({"path": asset["path"], "sha256": portable_manifest.sha256_file(target)})
    markers = root / "runtime" / "markers"
    markers.mkdir(parents=True)
    for name in ("homr_maintained_profile_commit.txt", "pdfscore_maintained_profile_commit.txt"):
        (markers / name).write_text("marker\n")
    return build_portable.write_manifest(
        root,
        snap,
        started=build_portable.dt.datetime(2026, 1, 1, tzinfo=build_portable.dt.timezone.utc),
        builder={"files": payload.check_running_builder(snap)},
        runtime={},
        distributions={},
        assets=assets,
        removed_scripts=[],
    )


def test_build_manifest_records_exact_provenance(snap, head, tmp_path: Path) -> None:
    manifest = json.loads(_portable(snap, tmp_path / "PDFScoreBar").read_text())
    assert manifest["schema_version"] == portable_manifest.MANIFEST_SCHEMA
    for key in ("source_commit", "application_source_commit", "builder_source_commit"):
        assert manifest[key] == head
    assert manifest["source_tree"] == _git("rev-parse", f"{head}^{{tree}}").decode().strip()
    blob = lambda path: hashlib.sha256(_git("cat-file", "blob", f"{head}:{path}")).hexdigest()  # noqa: E731
    assert manifest["application"]["manifest_sha256"] == blob(payload.MANIFEST)
    assert manifest["application"]["selector_sha256"] == blob("tools/materialize_distribution.py")
    assert manifest["builder"]["files"] == {p: blob(p) for p in payload.BUILDER_MODULES}
    assert manifest["windows_overlay"]["spec_sha256"] == blob(payload.OVERLAY_SPEC)
    assert manifest["pins"]["lock_sha256"] == blob(payload.LOCK)
    for entry in manifest["windows_overlay"]["files"]:
        assert entry["source_sha256"] == blob(entry["source"])
        assert manifest["files"][entry["path"]][1] == entry["sha256"]
    assert {p for p in manifest["files"] if p.startswith("app/")} == {f"app/{p}" for p in snap.app}


def test_verify_full_is_stable_and_the_launcher_reports_it(
    snap, tmp_path, monkeypatch, capsys
) -> None:
    root = tmp_path / "PDFScoreBar"
    _portable(snap, root)
    assert portable_manifest.verify(root, full=True) == []
    # Running the application leaves byte-code caches, which are not inventoried.
    (root / "app" / "src" / "__pycache__").mkdir()
    (root / "app" / "src" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"x")
    (root / "launcher" / "__pycache__").mkdir()
    assert portable_manifest.verify(root, full=True) == []
    monkeypatch.setattr(launcher, "ROOT", root)
    assert launcher.command_verify(SimpleArgs(full=True)) == 0
    assert json.loads(capsys.readouterr().out)["problems"] == []


class SimpleArgs:
    def __init__(self, **values):
        self.__dict__.update(values)


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ("extra_app", ["unexpected: app/tests/test_x.py"]),
        ("extra_launcher", ["unexpected: launcher/payload.py"]),
        ("missing_app", ["missing: app/models/mmr/mmr_classifier_best.pth"]),
        ("tampered_app", ["sha256 mismatch: app/src/pipeline/main.py"]),
        ("tampered_launcher", ["sha256 mismatch: launcher/launcher.py"]),
        ("extra_python", ["unexpected: python/Lib/site-packages/evil.py"]),
    ],
)
def test_verify_detects_extra_missing_and_tampered_files(
    snap, tmp_path, mutation, expected
) -> None:
    root = tmp_path / "PDFScoreBar"
    _portable(snap, root)
    if mutation == "extra_app":
        (root / "app" / "tests").mkdir()
        (root / "app" / "tests" / "test_x.py").write_text("x")
    elif mutation == "extra_launcher":
        (root / "launcher" / "payload.py").write_text("x")
    elif mutation == "missing_app":
        (root / "app" / "models" / "mmr" / "mmr_classifier_best.pth").unlink()
    elif mutation == "tampered_app":
        path = root / "app" / "src" / "pipeline" / "main.py"
        data = path.read_bytes()
        path.write_bytes(data[:-1] + (b"#" if data[-1:] != b"#" else b"!"))
    elif mutation == "tampered_launcher":
        path = root / "launcher" / "launcher.py"
        data = path.read_bytes()
        path.write_bytes(data[:-1] + (b"#" if data[-1:] != b"#" else b"!"))
    else:
        (root / "python" / "Lib" / "site-packages" / "evil.py").write_text("x")
    problems = portable_manifest.verify(root, full=True)
    for item in expected:
        assert item in problems, problems


def _rewrite(root: Path, change) -> None:
    path = root / portable_manifest.MANIFEST_PATH
    manifest = json.loads(path.read_text())
    change(manifest)
    manifest["tree_digest"] = portable_manifest.tree_digest(manifest["files"])
    path.write_text(json.dumps(manifest))


def _add_inventory(manifest: dict, name: str, data: bytes) -> None:
    manifest["files"][name] = [len(data), hashlib.sha256(data).hexdigest()]


@pytest.mark.parametrize(
    "change, expected",
    [
        # A consistently re-hashed inventory still has to match the application selection.
        (
            lambda m: _add_inventory(m, "app/tests/test_x.py", b"x"),
            "file outside the main application selection: app/tests/test_x.py",
        ),
        (
            lambda m: _add_inventory(m, "launcher/payload.py", b"x"),
            "file outside the Windows allowlist: launcher/payload.py",
        ),
        (
            lambda m: m["application"]["files"].update({"tests/test_x.py": "0" * 64}),
            "application file missing: tests/test_x.py",
        ),
        (
            lambda m: m["application"].update(source_commit="0" * 40),
            "application source commit differs",
        ),
        (
            lambda m: m["files"]["app/src/pipeline/main.py"].__setitem__(1, "0" * 64),
            "application file differs from the main selection: src/pipeline/main.py",
        ),
    ],
)
def test_contract_rejects_a_consistently_rewritten_manifest(
    snap, tmp_path, change, expected
) -> None:
    root = tmp_path / "PDFScoreBar"
    _portable(snap, root)
    if "tests/test_x.py" in expected and "app/" in expected:
        (root / "app" / "tests").mkdir()
        (root / "app" / "tests" / "test_x.py").write_text("x")
    if "launcher/payload.py" in expected:
        (root / "launcher" / "payload.py").write_text("x")
    _rewrite(root, change)
    problems = portable_manifest.verify(root, full=False)
    assert any(problem.startswith(expected) for problem in problems), problems
