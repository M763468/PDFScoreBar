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
OVERLAY = {
    "PDFScoreBar.cmd",
    "launcher/launcher.py",
    "launcher/manifest.py",
    "launcher/user_setup.py",
}


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
        "tools/windows_portable/user_setup.py",
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
    build_portable.write_addons_path(root)  # the relative add-ons .pth (#553)
    return build_portable.write_manifest(
        root,
        snap,
        started=build_portable.dt.datetime(2026, 1, 1, tzinfo=build_portable.dt.timezone.utc),
        builder={"files": payload.check_running_builder(snap)},
        runtime={},
        distributions={},
        assets=assets,
        removed_scripts=[],
        excluded=[],
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


# --- #553: first-run user setup (triton-windows from PyPI into addons/) -----------------
# The recipient installs triton-windows (with its NVIDIA ptxas/cuda.h/cuda.lib and TinyCC)
# from PyPI instead of receiving it in the folder. These run the real pip commands against
# a locally built stand-in wheel (no network) and simulate interruptions.

import base64  # noqa: E402
import contextlib  # noqa: E402
import shutil  # noqa: E402
import zipfile  # noqa: E402

user_setup = sys.modules["user_setup"]  # the module the launcher imports

PACKAGE = user_setup.SETUP_SPEC["packages"][0]
WHEEL_NAME = f"triton_windows-{PACKAGE['version']}-py3-none-any.whl"


def _wheel(directory: Path, *, version_text: str = "3.8.0", drop: str | None = None) -> Path:
    names = [*PACKAGE["required_files"], *user_setup.TOOLCHAIN_FILES]
    files = {name: f"stand-in {name}\n".encode() for name in names}
    files["triton/__init__.py"] = f"__version__ = {version_text!r}\n".encode()
    if drop:
        files.pop(drop)
    info = f"triton_windows-{PACKAGE['version']}.dist-info"
    files[f"{info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: triton-windows\nVersion: {PACKAGE['version']}\n"
    ).encode()
    files[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[f"{info}/entry_points.txt"] = b"[console_scripts]\nproton = triton:__init__\n"
    record = []
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record.append(f"{name},sha256={digest},{len(data)}")
    record.append(f"{info}/RECORD,,")
    files[f"{info}/RECORD"] = ("\n".join(record) + "\n").encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / WHEEL_NAME
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "PDFScoreBar"
    pth = root / user_setup.PTH_PATH
    pth.parent.mkdir(parents=True)
    pth.write_text(user_setup.PTH_LINE + "\n", encoding="utf-8")
    return root


class Recorder:
    """Run commands for real, but serve ``pip download`` from a local wheel (no network)."""

    def __init__(self, wheel_source: Path):
        self.wheel_source = wheel_source
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if command[3:6] == ["--isolated", "--disable-pip-version-check", "download"]:
            dest = Path(command[command.index("--dest") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.wheel_source, dest / self.wheel_source.name)
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.run(command, **kwargs)

    def downloads(self) -> int:
        return sum(1 for c in self.commands if "download" in c)

    def installs(self) -> int:
        return sum(1 for c in self.commands if "install" in c)


def _isolated_env(root: Path) -> dict[str, str]:
    """Environment of the real pip runs: no outside Python, pip or temp settings.

    Windows' own variables are kept: with an empty SYSTEMROOT, pip on Windows fails while
    setting up SSL (``ssl.SSLError: [SSL] unknown error``, #553 F2). Temporary files and
    pip's user cache stay below the test's directory.
    """

    temp = root.parent / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "", "PYTHONNOUSERSITE": "1", "TEMP": str(temp), "TMP": str(temp)}
    # pip resolves its user cache from these at import time; keep it below the test too.
    env |= {"TMPDIR": str(temp), "HOME": str(temp), "XDG_CACHE_HOME": str(temp / "cache")}
    for key in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def test_isolated_setup_env_keeps_the_windows_system_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("PIP_INDEX_URL", "https://elsewhere.invalid/simple")
    monkeypatch.setenv("PYTHONPATH", "/elsewhere")
    env = _isolated_env(tmp_path / "PDFScoreBar")
    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert not any(k.startswith("PIP_") for k in env) and "PYTHONPATH" not in env
    assert Path(env["TEMP"]).is_relative_to(tmp_path)


def _setup(root: Path, runner, **kwargs):
    lines: list[str] = []
    result = user_setup.run_setup(
        root,
        Path(sys.executable),
        env=_isolated_env(root) | kwargs.pop("extra_env", {}),
        assume_yes=kwargs.pop("assume_yes", True),
        gpu_smoke=kwargs.pop("gpu_smoke", False),
        runner=runner,
        out=lines.append,
        **kwargs,
    )
    return result, lines


def test_spec_names_the_concerned_nvidia_files_and_pins_a_known_version():
    lock = REPO / "tools" / "windows_portable" / "requirements-cu126.txt"
    pins = dict(
        line.strip().split("==", 1)
        for line in lock.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    assert pins[PACKAGE["name"]] == PACKAGE["version"]
    required = set(PACKAGE["required_files"])
    assert {
        "triton/backends/nvidia/bin/ptxas.exe",
        "triton/backends/nvidia/include/cuda.h",
        "triton/backends/nvidia/lib/x64/cuda.lib",
    } <= required
    excluded = {e["path"] for e in user_setup.SETUP_SPEC["build_exclusions"]}
    assert excluded == {
        "torch/lib/nvperf_host.dll",
        "torch/lib/cusolverMg64_11.dll",
        "cv2/opencv_videoio_ffmpeg4110_64.dll",
        "cv2/opencv_videoio_ffmpeg4140_64.dll",
    }
    assert user_setup.SETUP_SPEC["index_url"] == "https://pypi.org/simple"


def test_pth_line_points_from_site_packages_to_the_addons(tmp_path: Path):
    site = tmp_path / "root" / "python" / "Lib" / "site-packages"
    resolved = (site / user_setup.PTH_LINE).resolve()
    assert resolved == (tmp_path / "root" / user_setup.ADDONS_SITE).resolve()
    assert user_setup.PTH_PATH == "python/Lib/site-packages/pdfscorebar_addons.pth"


def test_setup_downloads_installs_records_and_is_not_repeated(folder: Path, tmp_path: Path):
    assert user_setup.addons_problems(folder)[0].startswith("First-run setup is not completed")
    assert user_setup.addons_problems(folder, required=False) == []
    runner = Recorder(_wheel(tmp_path / "pypi"))
    result, lines = _setup(folder, runner)
    assert result["completed"] is True
    download = next(c for c in runner.commands if "download" in c)
    assert download[:3] == [sys.executable, "-m", "pip"]
    for flag in ("--no-deps", "--only-binary=:all:"):
        assert flag in download
    assert download[download.index("--index-url") + 1] == "https://pypi.org/simple"
    assert f"{PACKAGE['name']}=={PACKAGE['version']}" in download
    site = folder / user_setup.ADDONS_SITE
    for name in PACKAGE["required_files"]:
        assert (site / name).is_file()
    assert not (site / "bin").exists()  # console scripts with absolute paths are dropped
    state = json.loads((folder / user_setup.STATE).read_text(encoding="utf-8"))
    assert state["packages"][0]["wheel"] == WHEEL_NAME
    assert state["packages"][0]["source"] == "https://pypi.org/simple"
    assert all(not Path(name).is_absolute() and ".." not in name for name in state["files"])
    assert (folder / user_setup.DOWNLOADS / WHEEL_NAME).is_file()
    assert not (folder / user_setup.STAGING).exists()
    assert user_setup.addons_problems(folder, full=True) == []
    assert any("PyPI" in line or "pypi.org" in line for line in lines)

    # A completed setup does nothing: no download, no reinstall.
    before = len(runner.commands)
    _, lines = _setup(folder, runner)
    assert len(runner.commands) == before
    assert "already completed" in lines[-1]

    # --force reinstalls from the kept wheel without downloading again.
    _setup(folder, runner, force=True)
    assert runner.downloads() == 1 and runner.installs() == 2


def test_setup_from_a_predownloaded_wheel_dir_needs_no_network(folder: Path, tmp_path: Path):
    wheels = tmp_path / "usb"
    _wheel(wheels)
    runner = Recorder(tmp_path / "unused.whl")
    result, _ = _setup(folder, runner, wheel_dir=wheels)
    assert result["packages"][0]["source"] == "wheel-dir"
    assert runner.downloads() == 0
    with pytest.raises(user_setup.SetupError, match="No triton-windows"):
        _setup(tmp_path / "other" / "PDFScoreBar", runner, wheel_dir=tmp_path / "empty")


def test_failed_setup_keeps_the_previous_installation(folder: Path, tmp_path: Path, monkeypatch):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    _setup(folder, runner)
    state_before = (folder / user_setup.STATE).read_bytes()

    monkeypatch.setattr(user_setup, "GPU_SMOKE", "raise SystemExit('no CUDA GPU')")
    with pytest.raises(user_setup.SetupError, match="GPU compile check failed"):
        _setup(folder, runner, force=True, gpu_smoke=True)
    assert (folder / user_setup.STATE).read_bytes() == state_before
    assert user_setup.addons_problems(folder, full=True) == []
    assert not (folder / user_setup.STAGING).exists()

    # A wheel without the NVIDIA files is rejected before anything is swapped in.
    (folder / user_setup.DOWNLOADS / WHEEL_NAME).unlink()
    broken = Recorder(_wheel(tmp_path / "broken", drop="triton/backends/nvidia/bin/ptxas.exe"))
    with pytest.raises(user_setup.SetupError, match="lacks required files"):
        _setup(folder, broken, force=True)
    assert user_setup.addons_problems(folder, full=True) == []


def test_cancelled_setup_changes_nothing(folder: Path, tmp_path: Path):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    with pytest.raises(user_setup.SetupError, match="cancelled"):
        user_setup.run_setup(
            folder,
            Path(sys.executable),
            env={},
            runner=runner,
            confirm=lambda prompt: "n",
            out=lambda line: None,
        )
    assert runner.commands == []
    assert not (folder / user_setup.STATE).exists()


def test_interrupted_swap_is_recovered_on_the_next_run(folder: Path, tmp_path: Path):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    _setup(folder, runner)
    # Simulate a crash after moving the old add-ons away but before the new ones arrived.
    (folder / user_setup.ADDONS_SITE).rename(folder / user_setup.PREVIOUS)
    (folder / user_setup.STAGING).mkdir()
    assert user_setup.addons_problems(folder)[0].startswith("add-on file missing")
    _, lines = _setup(folder, runner)
    assert "already completed" in lines[-1]
    assert not (folder / user_setup.PREVIOUS).exists()
    assert not (folder / user_setup.STAGING).exists()


def test_verify_detects_changed_addons_and_version_drift(folder: Path, tmp_path: Path):
    _setup(folder, Recorder(_wheel(tmp_path / "pypi")))
    ptxas = folder / user_setup.ADDONS_SITE / "triton/backends/nvidia/bin/ptxas.exe"
    data = ptxas.read_bytes()
    ptxas.write_bytes(data[::-1])  # same size: only --full sees it
    assert user_setup.addons_problems(folder) == []
    assert user_setup.addons_problems(folder, full=True) == [
        "add-on sha256 mismatch: triton/backends/nvidia/bin/ptxas.exe"
    ]
    ptxas.unlink()
    assert "add-on file missing: triton/backends/nvidia/bin/ptxas.exe" in (
        user_setup.addons_problems(folder)
    )
    state = json.loads((folder / user_setup.STATE).read_text(encoding="utf-8"))
    state["spec_sha256"] = "0" * 64
    (folder / user_setup.STATE).write_text(json.dumps(state), encoding="utf-8")
    assert any("setup --force" in p for p in user_setup.addons_problems(folder))
    (folder / user_setup.PTH_PATH).unlink()
    assert user_setup.addons_problems(folder) == [
        f"missing add-on path file: {user_setup.PTH_PATH}"
    ]


def test_setup_survives_moving_the_folder(folder: Path, tmp_path: Path):
    _setup(folder, Recorder(_wheel(tmp_path / "pypi")))
    moved = tmp_path / "moved" / "PDFScoreBar"
    moved.parent.mkdir()
    folder.rename(moved)
    assert user_setup.addons_problems(moved, full=True) == []
    # The relocated add-ons import through the shipped relative .pth path (-S: only the
    # stand-in site-packages, as in the portable whose python/ has no triton).
    site = moved / "python" / "Lib" / "site-packages"
    probe = "import site, sys; site.addsitedir(sys.argv[1]); import triton; print(triton.__file__)"
    found = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe, str(site)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert Path(found).resolve().is_relative_to((moved / user_setup.ADDONS_SITE).resolve())


def test_builder_ships_the_lock_without_setup_packages_and_checks_it(tmp_path, monkeypatch):
    text = (REPO / "tools/windows_portable/requirements-cu126.txt").read_text(encoding="utf-8")
    shipped = build_portable.shipped_lock(text)
    assert "triton-windows==" in text and "triton-windows" not in shipped
    assert len(shipped.splitlines()) == len(text.splitlines()) - 1
    pins = build_portable.read_lock()
    site = tmp_path / "site-packages"
    site.mkdir()

    def install(name: str, version: str) -> None:
        info = site / f"{name.replace('-', '_')}-{version}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n", encoding="utf-8")

    for name, version in pins.items():
        if name != "triton-windows":
            install(name, version)
    install("pip", "26.0.1")
    (site / "homr" / "transformer").mkdir(parents=True)
    assert "triton-windows" not in build_portable.check_distributions(site)
    install("triton-windows", pins["triton-windows"])
    with pytest.raises(RuntimeError, match="Setup-acquired packages must not be shipped"):
        build_portable.check_distributions(site)


def test_builder_removes_the_excluded_files_and_their_record_lines(tmp_path):
    site = tmp_path / "site-packages"
    record = site / "torch-2.14.0+cu126.dist-info" / "RECORD"
    record.parent.mkdir(parents=True)
    lines = ["torch/lib/keep.dll,sha256=x,1"]
    for entry in user_setup.SETUP_SPEC["build_exclusions"]:
        (site / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
        (site / entry["path"]).write_bytes(b"nvidia")
        lines.append(entry["path"] + ",sha256=y,6")
    record.write_text("\n".join(lines) + "\n", encoding="utf-8")
    removed = build_portable.remove_build_exclusions(site)
    assert [r["path"] for r in removed] == [
        e["path"] for e in user_setup.SETUP_SPEC["build_exclusions"]
    ]
    assert all(not (site / r["path"]).exists() and r["reason"] for r in removed)
    assert record.read_text(encoding="utf-8") == "torch/lib/keep.dll,sha256=x,1\n"
    with pytest.raises(RuntimeError, match="Excluded file not found"):
        build_portable.remove_build_exclusions(site)


def test_launcher_requires_setup_for_jobs_but_verify_stays_clean(
    snap, tmp_path, monkeypatch, capsys
):
    root = tmp_path / "PDFScoreBar"
    manifest = json.loads(_portable(snap, root).read_text())
    assert manifest["user_setup"]["packages"][0]["name"] == "triton-windows"
    assert manifest["user_setup"]["spec_sha256"] == user_setup.spec_digest()
    assert manifest["files"][user_setup.PTH_PATH]  # the .pth is part of the build
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "check_location", lambda: [])
    assert launcher.command_verify(SimpleArgs(full=False)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["setup"] == {"completed": False} and report["problems"] == []
    with pytest.raises(launcher.LauncherError):
        launcher.preflight(gpu=False)
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert problems and problems[0].startswith("First-run setup is not completed")


def test_gpu_probe_requires_triton_from_the_folder_addons(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    info = {
        "cuda_available": True,
        "vram_gib": 8.0,
        "ort_session_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    }

    def probe(location: Path):
        out = json.dumps(dict(info, triton_location=str(location)))
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, out + "\n", "")

    monkeypatch.setattr(launcher.subprocess, "run", probe(Path("/elsewhere/triton")))
    assert "not from this folder's add-ons" in launcher.check_gpu({})[1][0]
    inside = tmp_path / user_setup.ADDONS_SITE / "triton"
    inside.mkdir(parents=True)
    toolchain = user_setup.toolchain_environment(tmp_path / user_setup.ADDONS_SITE)
    info["triton_cc"] = toolchain["CC"]
    info["triton_cuda_bin"] = str(Path(toolchain["CUDA_PATH"]) / "bin")
    monkeypatch.setattr(launcher.subprocess, "run", probe(inside))
    assert launcher.check_gpu({})[1] == []


# --- #553 F1: Triton's TinyCC/CUDA live in addons/, outside sysconfig's platlib ----------
# triton-windows reads CC and CUDA_PATH before it searches python/Lib/site-packages, so
# every PDFScoreBar process gets both, derived from the folder's current location.

TOOLCHAIN_SMOKE = r"""
import os, pathlib
cc, cuda = pathlib.Path(os.environ["CC"]), pathlib.Path(os.environ["CUDA_PATH"])
assert cc.is_file() and cc.name == "tcc.exe", cc
assert (cuda / "bin" / "ptxas.exe").is_file() and (cuda / "include" / "cuda.h").is_file()
assert (cuda / "lib" / "x64" / "cuda.lib").is_file()
staging = pathlib.Path(os.environ["EXPECT_UNDER"])
assert cc.is_relative_to(staging) and cuda.is_relative_to(staging), (cc, cuda, staging)
assert "CUDA_HOME" not in os.environ
print("ok")
"""


def test_toolchain_environment_is_built_from_the_given_site_only(tmp_path):
    site = tmp_path / "C" / user_setup.ADDONS_SITE
    inherited = {"PATH": "x", "CC": "gcc", "cuda_path": r"C:\CUDA\v12.6", "CUDA_HOME": "/cuda"}
    env = user_setup.apply_toolchain_environment(inherited, site)
    assert env == {
        "PATH": "x",
        "CC": str(site / "triton" / "runtime" / "tcc" / "tcc.exe"),
        "CUDA_PATH": str(site / "triton" / "backends" / "nvidia"),
    }
    assert inherited["CC"] == "gcc"  # the caller's mapping is not changed
    assert len(user_setup.toolchain_problems(site)) == len(user_setup.TOOLCHAIN_FILES)
    for rel in user_setup.TOOLCHAIN_FILES:
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_bytes(b"x")
    assert user_setup.toolchain_problems(site) == []
    (site / "triton/runtime/tcc/tcc.exe").unlink()
    assert user_setup.toolchain_problems(site) == [
        "Triton toolchain is incomplete: triton/runtime/tcc/tcc.exe is missing"
    ]


def test_spec_toolchain_matches_what_triton_windows_looks_for():
    # windows_utils.check_and_find_cuda ("bundled" layout) and runtime/build.py's TinyCC.
    assert user_setup.TOOLCHAIN_ENV == {
        "CC": "triton/runtime/tcc/tcc.exe",
        "CUDA_PATH": "triton/backends/nvidia",
    }
    cuda = user_setup.TOOLCHAIN_ENV["CUDA_PATH"]
    for rel in ("bin/ptxas.exe", "include/cuda.h", "lib/x64/cuda.lib"):
        assert f"{cuda}/{rel}" in user_setup.TOOLCHAIN_FILES
    assert user_setup.TOOLCHAIN_ENV["CC"] in user_setup.TOOLCHAIN_FILES
    # The compile check of setup asks Triton itself which compiler and CUDA it resolves.
    assert "_find_compiler" in user_setup.GPU_SMOKE and "find_cuda" in user_setup.GPU_SMOKE
    assert "torch.compile" in user_setup.GPU_SMOKE


def test_setup_smoke_uses_the_staged_toolchain_and_the_launcher_the_installed_one(
    folder: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(user_setup, "GPU_SMOKE", TOOLCHAIN_SMOKE)
    staging = folder / user_setup.STAGING
    bogus = {"CC": "gcc", "CUDA_PATH": str(tmp_path / "toolkit"), "CUDA_HOME": "/cuda"}
    result, _ = _setup(
        folder,
        Recorder(_wheel(tmp_path / "pypi")),
        gpu_smoke=True,
        extra_env=bogus | {"EXPECT_UNDER": str(staging.resolve())},
    )
    assert result["completed"] is True
    assert user_setup.compile_check_problems(folder) == []
    site = folder / user_setup.ADDONS_SITE
    assert user_setup.toolchain_problems(site) == []
    installed = user_setup.toolchain_environment(site)
    assert Path(installed["CC"]).is_file()
    assert (Path(installed["CUDA_PATH"]) / "bin" / "ptxas.exe").is_file()


def test_setup_rejects_a_wheel_without_the_toolchain_and_keeps_the_previous(
    folder: Path, tmp_path: Path
):
    _setup(folder, Recorder(_wheel(tmp_path / "pypi")))
    state_before = (folder / user_setup.STATE).read_bytes()
    (folder / user_setup.DOWNLOADS / WHEEL_NAME).unlink()
    broken = Recorder(_wheel(tmp_path / "broken", drop="triton/runtime/tcc/libtcc.dll"))
    with pytest.raises(user_setup.SetupError, match="Triton toolchain is incomplete"):
        _setup(folder, broken, force=True)
    assert (folder / user_setup.STATE).read_bytes() == state_before
    assert user_setup.addons_problems(folder, full=True) == []
    assert not (folder / user_setup.STAGING).exists()


def test_installed_toolchain_loss_is_reported(folder: Path, tmp_path: Path):
    _setup(folder, Recorder(_wheel(tmp_path / "pypi")))
    site = folder / user_setup.ADDONS_SITE
    state = json.loads((folder / user_setup.STATE).read_text(encoding="utf-8"))
    del state["files"]["triton/runtime/tcc/include/stdio.h"]  # an older/partial record
    (folder / user_setup.STATE).write_text(json.dumps(state), encoding="utf-8")
    (site / "triton/runtime/tcc/include/stdio.h").unlink()
    assert user_setup.addons_problems(folder) == [
        "Triton toolchain is incomplete: triton/runtime/tcc/include/stdio.h is missing"
    ]
    assert user_setup.addons_problems(folder, required=False)  # verify reports it as well


def test_no_gpu_check_setup_is_refused_until_the_check_ran(
    folder: Path, tmp_path: Path, monkeypatch
):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    _setup(folder, runner)  # gpu_smoke=False: like --no-gpu-check
    assert user_setup.addons_problems(folder, full=True) == []  # integrity is fine
    assert "--no-gpu-check" in user_setup.compile_check_problems(folder)[0]
    # Repeating --no-gpu-check does nothing; a plain setup runs the check from the kept
    # wheel; a failing check keeps the existing installation and its record.
    _, lines = _setup(folder, runner)
    assert "already completed" in lines[-1]
    state_before = (folder / user_setup.STATE).read_bytes()
    monkeypatch.setattr(user_setup, "GPU_SMOKE", "raise SystemExit('Failed to find C compiler')")
    with pytest.raises(user_setup.SetupError, match="GPU compile check failed"):
        _setup(folder, runner, gpu_smoke=True)
    assert (folder / user_setup.STATE).read_bytes() == state_before
    assert user_setup.addons_problems(folder, full=True) == []
    monkeypatch.setattr(user_setup, "GPU_SMOKE", "print('ok')")
    _, lines = _setup(folder, runner, gpu_smoke=True)
    assert lines[0].startswith("The GPU compile check of the previous setup was skipped")
    assert user_setup.compile_check_problems(folder) == []
    assert runner.downloads() == 1
    _, lines = _setup(folder, runner, gpu_smoke=True)
    assert "already completed" in lines[-1]


def test_explicit_wheel_dir_wins_over_the_kept_wheel(folder: Path, tmp_path: Path, monkeypatch):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    _setup(folder, runner)
    kept = folder / user_setup.DOWNLOADS / WHEEL_NAME
    kept_bytes, state_before = kept.read_bytes(), (folder / user_setup.STATE).read_bytes()

    # A named directory without the wheel fails even though a kept wheel exists.
    with pytest.raises(user_setup.SetupError, match="No triton-windows"):
        _setup(folder, runner, force=True, wheel_dir=tmp_path / "empty")
    assert kept.read_bytes() == kept_bytes
    assert (folder / user_setup.STATE).read_bytes() == state_before

    # A named wheel whose check fails does not replace the kept wheel or the installation.
    usb = _wheel(tmp_path / "usb", version_text="3.8.0+usb")
    monkeypatch.setattr(user_setup, "GPU_SMOKE", "raise SystemExit('no CUDA GPU')")
    with pytest.raises(user_setup.SetupError, match="GPU compile check failed"):
        _setup(folder, runner, force=True, wheel_dir=usb.parent, gpu_smoke=True)
    assert kept.read_bytes() == kept_bytes
    assert (folder / user_setup.STATE).read_bytes() == state_before

    # A named wheel that passes is installed and becomes the kept wheel.
    result, _ = _setup(folder, runner, force=True, wheel_dir=usb.parent)
    assert result["packages"][0]["source"] == "wheel-dir"
    assert kept.read_bytes() == usb.read_bytes()
    assert "3.8.0+usb" in (folder / user_setup.ADDONS_SITE / "triton/__init__.py").read_text()
    assert sorted(p.name for p in (folder / user_setup.DOWNLOADS).iterdir()) == [WHEEL_NAME]
    assert runner.downloads() == 1


def test_interrupted_setup_cleans_up_and_keeps_the_previous(folder: Path, tmp_path: Path):
    runner = Recorder(_wheel(tmp_path / "pypi"))
    _setup(folder, runner)
    state_before = (folder / user_setup.STATE).read_bytes()

    def interrupted(command, **kwargs):
        if "install" in command:
            raise KeyboardInterrupt
        return runner(command, **kwargs)

    with pytest.raises(KeyboardInterrupt):
        _setup(folder, interrupted, force=True)
    assert not (folder / user_setup.STAGING).exists()
    assert (folder / user_setup.STATE).read_bytes() == state_before
    assert user_setup.addons_problems(folder, full=True) == []


def test_launcher_setup_reports_ctrl_c_without_a_traceback(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher, "check_location", lambda: [])
    monkeypatch.setattr(launcher, "verify", lambda root, full: [])
    monkeypatch.setattr(launcher, "jobs_root_lock", contextlib.nullcontext)
    monkeypatch.setattr(launcher, "child_environment", lambda: {})
    monkeypatch.setattr(launcher.user_setup, "run_setup", interrupted)
    assert launcher.main(["setup"]) == 130
    err = capsys.readouterr().err
    assert "interrupted" in err and "Traceback" not in err


def test_child_environment_points_triton_at_the_current_folder(snap, tmp_path: Path, monkeypatch):
    root = tmp_path / "PDFScoreBar"
    _portable(snap, root)
    monkeypatch.setenv("CC", "cl.exe")
    monkeypatch.setenv("CUDA_PATH", r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6")
    monkeypatch.setenv("CUDA_HOME", "/usr/local/cuda")
    for current in (root, tmp_path / "moved" / "PDFScoreBar"):
        if current != root:
            current.parent.mkdir()
            root.rename(current)
        monkeypatch.setattr(launcher, "ROOT", current)
        monkeypatch.setattr(launcher, "APP", current / "app")
        env = launcher.child_environment()
        site = current / user_setup.ADDONS_SITE
        assert env["CC"] == str(site / "triton" / "runtime" / "tcc" / "tcc.exe")
        assert env["CUDA_PATH"] == str(site / "triton" / "backends" / "nvidia")
        assert "CUDA_HOME" not in env
    assert os.environ["CC"] == "cl.exe"  # the launcher's own (and the system) env is kept


def test_gpu_probe_requires_triton_to_compile_with_the_folder_toolchain(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    inside = tmp_path / user_setup.ADDONS_SITE / "triton"
    inside.mkdir(parents=True)
    toolchain = user_setup.toolchain_environment(tmp_path / user_setup.ADDONS_SITE)
    good = {
        "cuda_available": True,
        "vram_gib": 8.0,
        "ort_session_providers": ["CUDAExecutionProvider"],
        "triton_location": str(inside),
        "triton_cc": toolchain["CC"],
        "triton_cuda_bin": str(Path(toolchain["CUDA_PATH"]) / "bin"),
    }

    def probe(**changes):
        out = json.dumps(good | changes)
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, out + "\n", "")

    monkeypatch.setattr(launcher.subprocess, "run", probe())
    assert launcher.check_gpu({})[1] == []
    for changes, expected in (
        ({"triton_cc": r"C:\VS\cl.exe"}, "not with the TinyCC"),
        ({"triton_cc": None}, "not with the TinyCC"),
        ({"triton_cuda_bin": r"C:\CUDA\v12.6\bin"}, "not the CUDA files"),
        ({"triton_cuda_bin": None}, "not the CUDA files"),
    ):
        monkeypatch.setattr(launcher.subprocess, "run", probe(**changes))
        problems = launcher.check_gpu({})[1]
        assert len(problems) == 1 and expected in problems[0], problems
    # The probe asks Triton without compiling anything.
    assert "_find_compiler" in launcher._GPU_PROBE and "torch.compile(" not in launcher._GPU_PROBE


def test_preflight_refuses_a_setup_without_its_gpu_check(snap, tmp_path, monkeypatch, capsys):
    root = tmp_path / "PDFScoreBar"
    _portable(snap, root)
    _setup(root, Recorder(_wheel(tmp_path / "pypi")))  # gpu_smoke=False
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "check_location", lambda: [])
    assert launcher.command_verify(SimpleArgs(full=True)) == 0
    capsys.readouterr()
    with pytest.raises(launcher.LauncherError):
        launcher.preflight(gpu=False)
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert len(problems) == 1 and "--no-gpu-check" in problems[0], problems
