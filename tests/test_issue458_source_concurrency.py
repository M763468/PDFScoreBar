import sys
import time
from pathlib import Path

import pytest
from PIL import Image

from src.pipeline.detection.source_concurrency import SourceJobs, select_workers


def test_admission(tmp_path):
    image = tmp_path / "page.png"
    Image.new("RGB", (100, 100)).save(image)
    policy = dict(
        workers=3, validated_workers=3, ram_gib=12, vram_gib=7, max_input_pixels=10000, device="gpu"
    )

    def choose(**kw):
        return select_workers(policy, [image, tmp_path / "other.png"], **kw)

    Image.new("RGB", (100, 100)).save(tmp_path / "other.png")
    args = dict(available_ram_gib=16, available_vram_gib=8, device="gpu")
    assert choose(**args)["selected_workers"] == 2
    for field, value in [("available_ram_gib", 1), ("available_vram_gib", 1), ("device", "cpu")]:
        with pytest.raises(RuntimeError):
            choose(**{**args, field: value})
    policy["on_unavailable"] = "serial"
    assert choose(**{**args, "device": "cpu"})["selected_workers"] == 1
    policy["max_input_pixels"] = 1
    assert "shape" in choose(**args)["reason"]


def test_order_and_bound(tmp_path):
    keys = [tmp_path / str(i) for i in range(6)]
    calls = []
    jobs = SourceJobs(5)

    def execute(key):
        calls.append(key)
        time.sleep(0.02 if key == keys[0] else 0.001)
        return key

    results = jobs.ordered(keys, execute, 2, tmp_path / "events")
    assert next(results) == (keys[0], keys[0])
    assert len(calls) == 2
    assert [key for key, _ in results] == keys[1:]


def test_duplicate(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        list(SourceJobs(1).ordered([tmp_path, tmp_path], lambda k: k, 2, tmp_path / "events"))


def test_timeout_kills_descendants(tmp_path):
    pid = tmp_path / "pid"
    script = f"import subprocess,time; p=subprocess.Popen(['sleep','60']); open({str(pid)!r},'w').write(str(p.pid)); time.sleep(60)"
    jobs = SourceJobs(0.3)
    with pytest.raises(TimeoutError):
        jobs.run([sys.executable, "-c", script])
    child = int(pid.read_text())
    # Orphan zombies can await init reaping, but cannot run or hold resources.
    status = Path(f"/proc/{child}/stat")
    assert not status.exists() or status.read_text().split()[2] == "Z"


def test_failure_cancels_running_and_queued(tmp_path):
    jobs = SourceJobs(5)
    keys = [tmp_path / str(i) for i in range(5)]
    calls = []

    def execute(key):
        calls.append(key)
        if key == keys[1]:
            time.sleep(0.1)
            raise RuntimeError("injected OOM/nonzero")
        jobs.run([sys.executable, "-c", "import time;time.sleep(60)"])

    start = time.monotonic()
    with pytest.raises(RuntimeError):
        list(jobs.ordered(keys, execute, 2, tmp_path / "events"))
    assert time.monotonic() - start < 2
    assert set(calls) == set(keys[:2])


def test_sigterm_cleans_worker(tmp_path):
    marker = tmp_path / "leader"
    script = """
import sys
from pathlib import Path
from src.pipeline.detection.source_concurrency import SourceJobs
root = Path(sys.argv[1])
jobs = SourceJobs(60)
def execute(key):
    return jobs.run([sys.executable, '-c', "import os,time;open(" + repr(str(root/'leader')) + ",'w').write(str(os.getpid()));time.sleep(60)"])
list(jobs.ordered([root/'a', root/'b'], execute, 1, root/'events'))
"""
    import signal
    import subprocess

    process = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)])
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        child = int(marker.read_text())
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=3) == 143
        assert not Path(f"/proc/{child}").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.mark.parametrize("case", ["duplicate", "missing", "unexpected"])
def test_sr_result_identity_rejected(tmp_path, monkeypatch, case):
    import json
    import subprocess

    from src.pipeline.detection import profile_sources_batch_sr as batch

    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    other = tmp_path / "other.png"
    other.write_bytes(b"image")
    sr = tmp_path / "sr.png"
    sr.write_bytes(b"sr")
    row = {"image": str(other if case == "unexpected" else image), "sr_image": str(sr)}
    rows = [row, row] if case == "duplicate" else [] if case == "missing" else [row]

    def run(command, **kwargs):
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "status": "completed",
                    "memory_boundary": "dedicated_sr_batch_process",
                    "historical_detector_artifact_runtime_input": False,
                    "outputs": rows,
                }
            )
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(batch.subprocess, "run", run)
    detector = batch.BatchSRProfileHybridDetector(
        det_cfg={"enable_sr": True, "sr_scale": 4},
        images=[image],
        run_id="fault",
        project_root=tmp_path,
        dry_run=False,
        skip_existing=False,
        profile_name="maintained_original",
    )
    with pytest.raises(ValueError):
        detector._batch_sr_worker(support_output=tmp_path / "support")


def test_failure_diagnostics_survive_engine_scratch_cleanup(tmp_path):
    import shutil

    from src.pipeline.detection.profile_sources_batch_sr import _retain_source_diagnostics

    scratch = tmp_path / ".engine-work"
    output = scratch / "hybrid/source_page_workers"
    log = output / "score/page/worker.log"
    log.parent.mkdir(parents=True)
    log.write_bytes(b"large line\n" * 20000 + b"timeout details\n")
    (output / "admission.json").write_text('{"selected_workers":2}')
    (output / "failure.json").write_text('{"error_type":"TimeoutError"}')
    _retain_source_diagnostics(output)
    shutil.rmtree(scratch)
    assert (tmp_path / "failed-source-admission.json").exists()
    assert "TimeoutError" in (tmp_path / "failed-source-failure.json").read_text()
    tail = (tmp_path / "failed-source-page-page.log").read_bytes()
    assert len(tail) <= 65536
    assert tail.endswith(b"timeout details\n")


def test_later_failure_is_not_hidden_by_earlier_cancel(tmp_path):
    jobs = SourceJobs(5)
    keys = [tmp_path / "first", tmp_path / "second"]

    def execute(key):
        if key == keys[1]:
            time.sleep(0.05)
            raise ValueError("original worker failure")
        return jobs.run([sys.executable, "-c", "import time;time.sleep(60)"])

    with pytest.raises(ValueError, match="original worker failure"):
        list(jobs.ordered(keys, execute, 2, tmp_path / "events"))
