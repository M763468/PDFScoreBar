import json
import multiprocessing
import os
from pathlib import Path

import pytest

from src.pipeline.detection.sr_compiler_cache import lease


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "cache"
    path.mkdir(mode=0o700)
    return path


def test_reuse_identity_and_environment(root):
    old = os.environ.get("TORCHINDUCTOR_CACHE_DIR")
    with lease(root, {"runtime": "one"}) as cold:
        Path(os.environ["TORCHINDUCTOR_CACHE_DIR"], "kernel").write_bytes(b"compiled")
    assert cold["state"] == "empty"
    assert os.environ.get("TORCHINDUCTOR_CACHE_DIR") == old
    with lease(root, {"runtime": "one"}) as warm:
        assert warm["state"] == "verified-reuse"
        assert warm["before"] == cold["after"]
    with lease(root, {"runtime": "two"}) as changed:
        assert changed["state"] == "empty"
        assert changed["key"] != warm["key"]


def test_corruption_and_manifest_mismatch(root):
    with lease(root, {"runtime": "one"}) as run:
        Path(os.environ["TRITON_CACHE_DIR"], "kernel").write_bytes(b"compiled")
    entry = Path(run["entry"])
    (entry / "triton/kernel").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        with lease(root, {"runtime": "one"}):
            pytest.fail("corrupt cache accepted")
    manifest = json.loads((entry / "manifest.json").read_text())
    manifest["identity"]["runtime"] = "mixed"
    (entry / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="identity"):
        with lease(root, {"runtime": "one"}):
            pass


def test_interrupted_writer(root):
    with pytest.raises(RuntimeError):
        with lease(root, {}):
            raise RuntimeError("failed worker")
    with pytest.raises(ValueError, match="Interrupted"):
        with lease(root, {}):
            pass


def test_permissions_unavailable_and_symlink(root):
    root.chmod(0o755)
    with pytest.raises(PermissionError):
        with lease(root, {}):
            pass
    with pytest.raises(FileNotFoundError):
        with lease(root / "absent", {}):
            pass
    root.chmod(0o700)
    alias = root.parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        with lease(alias, {}):
            pass


def _contend(root, result):
    try:
        with lease(root, {}):
            result.put("unexpected success")
    except BlockingIOError:
        result.put("busy")


def test_concurrent_job_rejected(root):
    # spawn avoids inheriting the parent's open flock file descriptor.
    ctx = multiprocessing.get_context("spawn")
    result = ctx.Queue()
    with lease(root, {}):
        child = ctx.Process(target=_contend, args=(root, result))
        child.start()
        child.join(10)
        assert child.exitcode == 0
        assert result.get(timeout=1) == "busy"
    with lease(root, {}):
        pass


def test_unattributed_cache_and_symlink_entry(root):
    with lease(root, {}) as run:
        pass
    entry = Path(run["entry"])
    (entry / "manifest.json").unlink()
    with pytest.raises(ValueError, match="Unattributed"):
        with lease(root, {}):
            pass


def test_uid_mismatch(root, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 123456)
    with pytest.raises(PermissionError):
        with lease(root, {}):
            pass


def test_relative_root_rejected():
    with pytest.raises(ValueError, match="absolute"):
        with lease(Path("relative"), {}):
            pass


def test_gid_separation(root, monkeypatch):
    with lease(root, {}) as first:
        pass
    monkeypatch.setattr(os, "getgid", lambda: 123456)
    with lease(root, {}) as second:
        assert second["state"] == "empty"
        assert first["key"] != second["key"]


def test_symlink_artifact(root):
    with pytest.raises(ValueError, match="symlink"):
        with lease(root, {}):
            Path(os.environ["TRITON_CACHE_DIR"], "unsafe").symlink_to("/etc/passwd")


def _crash(root):
    with lease(root, {}):
        os._exit(7)


def test_process_crash_leaves_dirty_and_releases_lock(root):
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(target=_crash, args=(root,))
    child.start()
    child.join(10)
    assert child.exitcode == 7
    with pytest.raises(ValueError, match="Interrupted"):
        with lease(root, {}):
            pass
