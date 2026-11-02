"""Inactive job handoff candidate; never selected by the maintained production route.

The caller owns fresh SR validation and the outer job/container lifetime. This
module owns one bounded OMR process group and a hash-bound complete publication.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "pdfscorebar.omr_job.v1"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_publish(path, data):
    """Publish complete bytes without replacing an existing artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute_worker(command, log, timeout):
    """Terminate and reap the process group on timeout or coordinator SIGTERM."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("job phase must own cancellation on the main thread")
    if not 0 < timeout < float("inf"):
        raise ValueError("timeout must be finite and positive")

    def cancelled(signum, frame):
        raise InterruptedError("OMR phase cancelled by SIGTERM")

    previous = signal.signal(signal.SIGTERM, cancelled)
    process = None
    try:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        code = process.wait(timeout=timeout)
        if code:
            raise subprocess.CalledProcessError(code, command)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("worker exited leaving descendants")
    except BaseException:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            # The leader may already have exited while descendants ignored TERM.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def prediction_bytes(path):
    data = Path(path).read_bytes()
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("predictions must be a list")
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
            # Match hybrid_consensus.load_json_boxes: clipping at image edges
            # can produce zero extent; preserve the producer's bytes unchanged.
            or row[0] > row[2]
            or row[1] > row[3]
        ):
            raise ValueError("invalid source-coordinate barline")
    return data


@dataclass(frozen=True)
class Handoff:
    manifest: Path
    manifest_sha256: str
    run_id: str
    model: Path
    model_sha256: str


def build(
    images,
    sr_outputs,
    directory,
    *,
    run_id,
    model,
    model_sha256,
    timeout=900,
    execute=execute_worker,
):
    """Only a successful worker plus unchanged identities can publish complete."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    try:
        if str(uuid.UUID(run_id)) != run_id or uuid.UUID(run_id).version != 4:
            raise ValueError("run_id must be a fresh canonical UUID4 from the job owner")
        images = [Path(p).resolve() for p in images]
        if not images or len({p.stem for p in images}) != len(images):
            raise ValueError("ordered pages require unique stems")
        model = Path(model).resolve()
        if digest(model) != model_sha256:
            raise ValueError("model identity mismatch")
        by_image = {Path(row["image"]).resolve(): row for row in sr_outputs}
        if len(by_image) != len(sr_outputs) or set(by_image) != set(images):
            raise ValueError("SR page association mismatch")
        staged = directory / "sr"
        staged.mkdir()
        rows = []
        for image in images:
            if by_image[image].get("job_run_id") != run_id or by_image[image].get(
                "image_sha256"
            ) != digest(image):
                raise ValueError("SR/source run identity mismatch")
            sr = Path(by_image[image]["sr_image"]).resolve()
            if digest(sr) != by_image[image]["sr_sha256"]:
                raise ValueError("fresh SR identity mismatch")
            (staged / (image.stem + ".png")).symlink_to(sr)
            rows.append(
                {
                    "image": str(image),
                    "image_sha256": digest(image),
                    "sr_image": str(sr),
                    "sr_sha256": digest(sr),
                }
            )
        request = {
            "schema": SCHEMA,
            "run_id": run_id,
            "model": str(model),
            "model_sha256": model_sha256,
            "rows": rows,
            "runtime": {
                "uid": os.getuid(),
                "gid": os.getgid(),
                "image_id": os.environ.get("PDFSCORE_DOCKER_IMAGE_ID"),
            },
            "sr_base": str(staged),
            "output_dir": str(directory / "predictions"),
        }
        request_path = directory / "request.json"
        request_data = (json.dumps(request, indent=2) + "\n").encode()
        atomic_publish(request_path, request_data)
        request_digest = hashlib.sha256(request_data).hexdigest()
        result_path = directory / "worker-result.json"
        command = [
            sys.executable,
            "-m",
            "tools.issue459.job_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (directory / "worker.log").open("w") as log:
            execute(command, log, timeout)
        if digest(request_path) != request_digest:
            raise ValueError("request changed during worker execution")
        result = json.loads(result_path.read_text())
        if (
            result.get("schema") != SCHEMA
            or result.get("status") != "completed"
            or result.get("run_id") != run_id
            or result.get("request_sha256") != request_digest
            or result.get("model_sha256") != model_sha256
            or len(result.get("rows", [])) != len(rows)
        ):
            raise ValueError("worker result run/request/model mismatch")
        actual_runtime = result.get("runtime", {})
        if any(actual_runtime.get(key) != value for key, value in request["runtime"].items()):
            raise ValueError("worker runtime mismatch")
        if digest(model) != model_sha256:
            raise ValueError("model changed during worker execution")
        for row, attested in zip(rows, result["rows"]):
            if any(attested.get(key) != value for key, value in row.items()):
                raise ValueError("worker page association mismatch")
            if (
                digest(row["image"]) != row["image_sha256"]
                or digest(row["sr_image"]) != row["sr_sha256"]
            ):
                raise ValueError("input changed during worker execution")
            prediction = directory / "predictions" / Path(row["image"]).stem / "predictions.json"
            if not prediction.resolve().is_relative_to(directory / "predictions"):
                raise ValueError("prediction outside job directory")
            data = prediction_bytes(prediction)
            prediction_digest = hashlib.sha256(data).hexdigest()
            if (
                attested.get("predictions") != str(prediction)
                or attested.get("predictions_sha256") != prediction_digest
            ):
                raise ValueError("worker prediction attestation mismatch")
            row.update(predictions=str(prediction), predictions_sha256=prediction_digest)
        payload = {
            "schema": SCHEMA,
            "status": "completed",
            "run_id": run_id,
            "model": str(model),
            "model_sha256": model_sha256,
            "rows": rows,
            "runtime": actual_runtime,
            "worker_result": str(result_path),
            "worker_result_sha256": digest(result_path),
            "request_sha256": request_digest,
        }
        manifest = directory / "completed.json"
        data = (json.dumps(payload, indent=2) + "\n").encode()
        manifest_digest = hashlib.sha256(data).hexdigest()
        atomic_publish(manifest, data)
        return Handoff(manifest, manifest_digest, run_id, model, model_sha256)
    except BaseException as exc:
        atomic_publish(
            directory / "failed.json",
            (
                json.dumps(
                    {
                        "status": "failed",
                        "run_id": run_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                + "\n"
            ).encode(),
        )
        raise


def consume(handoff, image, sr_image, output):
    """Validate every row before atomically exposing any prediction to a consumer."""
    raw = handoff.manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != handoff.manifest_sha256:
        raise ValueError("manifest changed")
    payload = json.loads(raw)
    if (
        payload.get("schema") != SCHEMA
        or payload.get("status") != "completed"
        or payload.get("run_id") != handoff.run_id
        or payload.get("model") != str(handoff.model)
        or payload.get("model_sha256") != handoff.model_sha256
        or digest(handoff.model) != handoff.model_sha256
    ):
        raise ValueError("handoff run/model/status mismatch")
    if digest(payload["worker_result"]) != payload["worker_result_sha256"]:
        raise ValueError("worker attestation changed")
    selected = []
    seen = set()
    for row in payload["rows"]:
        if row["image"] in seen:
            raise ValueError("duplicate page identity")
        seen.add(row["image"])
        prediction = Path(row["predictions"]).resolve()
        if not prediction.is_relative_to(handoff.manifest.parent / "predictions"):
            raise ValueError("prediction outside job directory")
        if (
            digest(row["image"]) != row["image_sha256"]
            or digest(row["sr_image"]) != row["sr_sha256"]
        ):
            raise ValueError("input identity changed")
        data = prediction_bytes(prediction)
        if hashlib.sha256(data).hexdigest() != row["predictions_sha256"]:
            raise ValueError("prediction identity changed")
        if Path(row["image"]) == Path(image).resolve():
            if Path(row["sr_image"]) != Path(sr_image).resolve():
                raise ValueError("SR association mismatch")
            selected.append(data)
    if len(selected) != 1:
        raise ValueError("page not uniquely bound to this job")
    atomic_publish(Path(output), selected[0])
