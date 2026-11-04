"""Production OMR job protocol (ported from the Issue #459 research candidate)."""

import dataclasses
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from src.pipeline.detection.omr_job import build as _build
from src.pipeline.detection.omr_job import consume, digest, execute_worker


def build(*args, **kwargs):
    kwargs.setdefault(
        "worker_command", [sys.executable, "-m", "src.pipeline.detection.omr_job_worker"]
    )
    return _build(*args, **kwargs)


def inputs(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    images, sr = [], []
    for index in range(2):
        image = tmp_path / f"page{index}.png"
        image.write_bytes(f"source{index}".encode())
        support = tmp_path / f"sr{index}.png"
        support.write_bytes(f"fresh SR{index}".encode())
        images.append(image)
        sr.append(
            {
                "image": str(image),
                "sr_image": str(support),
                "sr_sha256": digest(support),
                "image_sha256": digest(image),
                "job_run_id": run_id,
            }
        )
    model = tmp_path / "model.pt"
    model.write_bytes(b"verified model")
    return images, sr, model


def worker(command, log, timeout, **kwargs):
    from src.pipeline.detection.omr_job_worker import run

    def infer(images, *, output_dir, **kwargs):
        outputs = []
        for image in images:
            page = output_dir / image.stem
            page.mkdir(parents=True)
            prediction = page / "predictions.json"
            prediction.write_text("[[1,2,3,4]]")
            outputs.append(prediction)
        return outputs

    run(
        Path(command[command.index("--request") + 1]),
        Path(command[command.index("--result") + 1]),
        infer=infer,
    )


def prepared(tmp_path, execute=worker):
    images, sr, model = inputs(tmp_path)
    handoff = build(
        images,
        sr,
        tmp_path / "phase",
        run_id=sr[0]["job_run_id"],
        model=model,
        model_sha256=digest(model),
        execute=execute,
    )
    return images, sr, model, handoff


def test_ordered_complete_handoff_copies_exact_bytes_without_overwrite(tmp_path):
    images, sr, model, handoff = prepared(tmp_path)
    manifest = json.loads(handoff.manifest.read_text())
    assert [row["image"] for row in manifest["rows"]] == [str(p) for p in images]
    output = tmp_path / "published.json"
    consume(handoff, images[1], sr[1]["sr_image"], output)
    assert output.read_bytes() == b"[[1,2,3,4]]"
    with pytest.raises(FileExistsError):
        consume(handoff, images[1], sr[1]["sr_image"], output)


@pytest.mark.parametrize("change", ["source", "sr", "model", "prediction", "manifest", "run"])
def test_any_tampered_identity_rejects_even_when_consuming_another_page(tmp_path, change):
    images, sr, model, handoff = prepared(tmp_path)
    if change == "source":
        images[1].write_bytes(b"changed")
    elif change == "sr":
        Path(sr[1]["sr_image"]).write_bytes(b"changed")
    elif change == "model":
        model.write_bytes(b"changed")
    elif change == "prediction":
        (handoff.manifest.parent / "predictions/page1/predictions.json").write_text("[]")
    elif change == "manifest":
        handoff.manifest.write_text("{}")
    else:
        handoff = dataclasses.replace(handoff, run_id=str(uuid.uuid4()))
    output = tmp_path / "published.json"
    with pytest.raises(ValueError):
        consume(handoff, images[0], sr[0]["sr_image"], output)
    assert not output.exists()


@pytest.mark.parametrize(
    "fault", ["exit7", "missing", "malformed", "partial", "changed_sr", "mixed_run"]
)
def test_worker_fault_cannot_publish_complete_and_retains_diagnostics(tmp_path, fault):
    images, sr, model = inputs(tmp_path)

    def failed(command, log, timeout, **kwargs):
        log.write("retained diagnostic\n")
        if fault == "exit7":
            raise subprocess.CalledProcessError(7, command)
        if fault == "missing":
            return
        worker(command, log, timeout)
        output = tmp_path / "phase/predictions/page1/predictions.json"
        if fault == "malformed":
            output.write_text("[[1,2,NaN,4]]")
        elif fault == "partial":
            output.unlink()
        elif fault == "mixed_run":
            result = tmp_path / "phase/worker-result.json"
            payload = json.loads(result.read_text())
            payload["run_id"] = str(uuid.uuid4())
            result.write_text(json.dumps(payload))
        else:
            Path(sr[1]["sr_image"]).write_bytes(b"changed")

    with pytest.raises((ValueError, FileNotFoundError, subprocess.CalledProcessError)):
        build(
            images,
            sr,
            tmp_path / "phase",
            run_id=sr[0]["job_run_id"],
            model=model,
            model_sha256=digest(model),
            execute=failed,
        )
    assert not (tmp_path / "phase/completed.json").exists()
    assert (tmp_path / "phase/failed.json").is_file()
    assert "retained diagnostic" in (tmp_path / "phase/worker.log").read_text()


def test_timeout_kills_and_reaps_a_worker_that_ignores_sigterm(tmp_path):
    pidfile = tmp_path / "pid"
    code = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    with (tmp_path / "worker.log").open("w") as log:
        with pytest.raises(subprocess.TimeoutExpired):
            execute_worker([sys.executable, "-c", code], log, 1)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_sigterm_cancellation_terminates_worker_and_restores_handler(tmp_path):
    import signal
    import threading
    import time

    pidfile = tmp_path / "pid"
    code = (
        "import os,time; from pathlib import Path; "
        f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    previous = signal.getsignal(signal.SIGTERM)

    def cancel_when_started():
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if pidfile.exists():
            os.kill(os.getpid(), signal.SIGTERM)

    thread = threading.Thread(target=cancel_when_started)
    thread.start()
    try:
        with (tmp_path / "worker.log").open("w") as log:
            with pytest.raises(InterruptedError):
                execute_worker([sys.executable, "-c", code], log, 10)
    finally:
        thread.join(5)
    assert signal.getsignal(signal.SIGTERM) == previous
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_failed_directory_cannot_be_reused_but_fresh_job_recovers(tmp_path):
    images, sr, model = inputs(tmp_path)

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(137, ["worker"])

    with pytest.raises(subprocess.CalledProcessError):
        build(
            images,
            sr,
            tmp_path / "failed",
            run_id=sr[0]["job_run_id"],
            model=model,
            model_sha256=digest(model),
            execute=failed,
        )
    with pytest.raises(FileExistsError):
        build(
            images,
            sr,
            tmp_path / "failed",
            run_id=sr[0]["job_run_id"],
            model=model,
            model_sha256=digest(model),
            execute=worker,
        )
    images, sr, model = inputs(tmp_path / "new_inputs")
    recovered = build(
        images,
        sr,
        tmp_path / "fresh",
        run_id=sr[0]["job_run_id"],
        model=model,
        model_sha256=digest(model),
        execute=worker,
    )
    assert recovered.manifest.exists()


def test_zero_extent_clipped_edges_preserve_existing_strict_consensus_contract(tmp_path):
    from src.pipeline.detection.omr_job import prediction_bytes
    from src.pipeline.steps.hybrid_consensus import load_json_boxes

    prediction = tmp_path / "edge.json"
    data = b"[[0,1166,0,1622],[1,2,3,2]]"
    prediction.write_bytes(data)
    assert load_json_boxes(prediction) == [(0, 1166, 0, 1622), (1, 2, 3, 2)]
    assert prediction_bytes(prediction) == data
