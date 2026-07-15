import hashlib
from pathlib import Path

from tools.issue245 import run_local_homr_snapshot_probe_entrypoint as entrypoint


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_sha256_probe_file_normalizes_crlf_for_archived_text(tmp_path: Path) -> None:
    path = tmp_path / "build_context" / "homr" / "autocrop.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"first\r\nsecond\r\n")

    assert entrypoint.sha256_probe_file(path) == digest(b"first\nsecond\n")


def test_sha256_probe_file_keeps_binary_hash_raw(tmp_path: Path) -> None:
    path = tmp_path / "build_context" / "homr" / "segmentation" / "model.onnx"
    path.parent.mkdir(parents=True)
    content = b"binary\r\nbytes\x00"
    path.write_bytes(content)

    assert entrypoint.sha256_probe_file(path) == digest(content)


def test_sha256_probe_file_keeps_text_outside_build_context_raw(tmp_path: Path) -> None:
    path = tmp_path / "other" / "autocrop.py"
    path.parent.mkdir(parents=True)
    content = b"first\r\nsecond\r\n"
    path.write_bytes(content)

    assert entrypoint.sha256_probe_file(path) == digest(content)
