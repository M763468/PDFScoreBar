"""Fail-closed fresh-run OMR handoff tests; no model or GPU required."""

import json
import subprocess
from pathlib import Path

import pytest

from tools.issue447.omr_reuse_poc import build_manifest, consume, digest
from tools.issue447.pipeline_poc import OrderedJobs


def fixtures(tmp_path):
    image, sr = tmp_path / "page.png", tmp_path / "sr.png"
    image.write_bytes(b"original")
    sr.write_bytes(b"fresh SR")
    row = {"image": str(image), "sr_image": str(sr), "sr_sha256": digest(sr)}

    def execute(command, **kwargs):
        output = Path(command[command.index("--output-dir") + 1]) / image.stem
        output.mkdir(parents=True)
        (output / "predictions.json").write_text("[[1, 2, 3, 4]]\n")

    manifest = build_manifest([image], [row], tmp_path / "phase", execute)
    return image, sr, manifest


def test_handoff_preserves_ordered_predictions_and_rejects_overwrite(tmp_path):
    image, sr, manifest = fixtures(tmp_path)
    output = tmp_path / "out/predictions.json"
    consume(manifest, image, sr, output)
    assert json.loads(output.read_text()) == [[1, 2, 3, 4]]
    with pytest.raises(FileExistsError):
        consume(manifest, image, sr, output)


@pytest.mark.parametrize(
    "corruption", ["image", "sr", "predictions", "status", "association", "missing"]
)
def test_invalid_handoff_never_publishes_or_falls_back(tmp_path, corruption):
    image, sr, manifest = fixtures(tmp_path)
    payload = json.loads(manifest.read_text())
    if corruption in ("image", "sr"):
        (image if corruption == "image" else sr).write_bytes(b"changed")
    elif corruption == "predictions":
        Path(payload["rows"][0]["predictions"]).write_text("[]")
    elif corruption == "status":
        payload["status"] = "failed"
        manifest.write_text(json.dumps(payload))
    elif corruption == "association":
        payload["rows"][0]["image"] = str(tmp_path / "wrong.png")
        manifest.write_text(json.dumps(payload))
    else:
        Path(payload["rows"][0]["predictions"]).unlink()
    output = tmp_path / "out/predictions.json"
    with pytest.raises((ValueError, FileNotFoundError)):
        consume(manifest, image, sr, output)
    assert not output.exists()


def test_failed_omr_process_cannot_publish_completed_manifest(tmp_path):
    image, sr = tmp_path / "page.png", tmp_path / "sr.png"
    image.write_bytes(b"source")
    sr.write_bytes(b"SR")

    def failed(command, **kwargs):
        raise subprocess.CalledProcessError(7, command)

    with pytest.raises(subprocess.CalledProcessError):
        build_manifest(
            [image],
            [{"image": str(image), "sr_image": str(sr), "sr_sha256": digest(sr)}],
            tmp_path / "failed",
            failed,
        )
    assert not (tmp_path / "failed/completed.json").exists()


def test_source_failure_cancels_queued_work_and_joins_running_children():
    # One worker makes later tasks deterministically pending behind the failure.
    import threading

    release, entered = threading.Event(), threading.Event()
    seen = []

    def execute(key):
        seen.append(key)
        if key == 0:
            entered.set()
            assert release.wait(2)
            raise RuntimeError("failed source")
        return key

    pool = OrderedJobs(range(3), execute, 1)
    assert entered.wait(2)
    pool.futures[2].cancel()
    release.set()
    with pytest.raises(RuntimeError):
        pool.result(0)
    pool.close()
    assert 2 not in seen
    assert all(f.done() for f in pool.futures.values())
