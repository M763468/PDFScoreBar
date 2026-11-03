"""Per-job OMR-DLN reuse: one model lifetime for the ordered pages of a job.

Ported from the Issue #459 research candidate (PR #478)
that passed the adoption-v2 performance, correctness and kill/OOM recovery gates
for root multi-page jobs. The route is chosen once, before the job starts
(:func:`select_route`); there is no fallback from the job route to the per-page
route after a failure.

Contract:

* the caller records source/model identity before SR and validates fresh SR;
* one dedicated worker process group loads the verified production checkpoint on
  CUDA once and writes predictions for every ordered page;
* only a successful worker exit plus unchanged run/request/model/input/prediction
  identities publishes ``completed.json``; otherwise ``failed.json`` and the
  partial diagnostics remain and no consumer can read any prediction;
* consumers pin the manifest digest and verify every row before atomically
  exposing exact prediction bytes, without overwriting.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA = "pdfscorebar.omr_job.v1"
ROUTE_PER_PAGE = "per_page"
ROUTE_JOB = "job_reuse"
_MODES = ("off", "auto")


def select_route(
    policy: Mapping[str, Any] | None,
    *,
    page_count: int,
    uid: int,
    model_validation: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Decide the OMR route before the job starts; never changes after a failure.

    ``auto`` selects the job route only inside the measured envelope: at least
    ``min_pages`` pages, a process UID listed in ``allowed_uids`` (root by
    default) and production model selection. Everything else keeps the existing
    per-page route explicitly.
    """
    policy = dict(policy or {})
    unknown = set(policy) - {"mode", "min_pages", "allowed_uids", "timeout_sec"}
    if unknown:
        raise ValueError(f"Unknown detection.omr_job_reuse keys: {sorted(unknown)}")
    mode = policy.get("mode", "off")
    if mode not in _MODES:
        raise ValueError(f"detection.omr_job_reuse.mode must be one of {_MODES}")
    min_pages = policy.get("min_pages", 2)
    if type(min_pages) is not int or min_pages < 2:
        raise ValueError("detection.omr_job_reuse.min_pages must be an integer >= 2")
    allowed = policy.get("allowed_uids", [0])
    if not isinstance(allowed, list) or not allowed or any(type(v) is not int for v in allowed):
        raise ValueError("detection.omr_job_reuse.allowed_uids must be a nonempty integer list")
    timeout = policy.get("timeout_sec", 900)
    if type(timeout) not in (int, float) or not 0 < timeout < float("inf"):
        raise ValueError("detection.omr_job_reuse.timeout_sec must be finite and positive")
    decision = {
        "route": ROUTE_PER_PAGE,
        "mode": mode,
        "page_count": page_count,
        "uid": uid,
        "min_pages": min_pages,
        "allowed_uids": allowed,
        "timeout_sec": timeout,
    }
    if mode == "off":
        reason = "disabled"
    elif dry_run:
        reason = "dry run"
    elif model_validation != "production":
        reason = "non-production model selection"
    elif page_count < min_pages:
        reason = "fewer pages than min_pages"
    elif uid not in allowed:
        reason = "process uid outside allowed_uids"
    else:
        decision.update(route=ROUTE_JOB, reason="measured envelope")
        return decision
    decision["reason"] = reason
    return decision


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_publish(path: str | Path, data: bytes) -> None:
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


def execute_worker(command, log, timeout, *, cwd=None, env=None) -> None:
    """Run the worker in its own process group; kill and reap it on any failure."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("OMR job phase must own cancellation on the main thread")
    if not 0 < timeout < float("inf"):
        raise ValueError("timeout must be finite and positive")

    def cancelled(signum, frame):
        raise InterruptedError("OMR job phase cancelled by SIGTERM")

    previous = signal.signal(signal.SIGTERM, cancelled)
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=cwd,
            env=env,
        )
        code = process.wait(timeout=timeout)
        if code:
            raise subprocess.CalledProcessError(code, command)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("OMR job worker exited leaving descendants")
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
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def prediction_bytes(path: str | Path) -> bytes:
    """Validate source-coordinate barlines with the strict consensus contract."""
    data = Path(path).read_bytes()
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("predictions must be a list")
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
            # Clipping at image edges can produce zero extent (hybrid_consensus).
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

    def to_request(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}

    @classmethod
    def from_request(cls, payload: Mapping[str, Any]) -> Handoff:
        if not isinstance(payload, Mapping):
            raise ValueError("precomputed_omr must be a mapping")
        return cls(
            manifest=Path(str(payload["manifest"])),
            manifest_sha256=str(payload["manifest_sha256"]),
            run_id=str(payload["run_id"]),
            model=Path(str(payload["model"])),
            model_sha256=str(payload["model_sha256"]),
        )


def bind_sources(images: Sequence[Path]) -> dict[str, Any]:
    """Record the job identity and source digests before SR starts."""
    return {
        "run_id": str(uuid.uuid4()),
        "inputs": {str(Path(p).resolve()): digest(p) for p in images},
    }


def bind_sr(
    binding: Mapping[str, Any],
    sr_by_image: Mapping[Path, Mapping[str, Any]],
    *,
    support_output: Path,
    expected_outputs: Mapping[Path, Path],
) -> list[dict[str, Any]]:
    """Require unchanged sources and this job's fresh SR outputs."""
    inputs = binding["inputs"]
    if {str(p) for p in expected_outputs} != set(inputs) or set(map(str, sr_by_image)) != set(
        inputs
    ):
        raise ValueError("SR page association mismatch")
    rows = []
    for image_text, expected_digest in inputs.items():
        image = Path(image_text)
        if digest(image) != expected_digest:
            raise ValueError(f"source changed during SR: {image}")
        item = sr_by_image[image]
        sr_image = Path(str(item["sr_image"])).resolve()
        if sr_image != Path(expected_outputs[image]).resolve() or not sr_image.is_relative_to(
            Path(support_output).resolve()
        ):
            raise ValueError(f"SR result is not this job's fresh output: {image}")
        rows.append(
            {
                **item,
                "image": str(image),
                "image_sha256": expected_digest,
                "job_run_id": binding["run_id"],
            }
        )
    return rows


def build(
    images: Sequence[Path],
    sr_outputs: Sequence[Mapping[str, Any]],
    directory: Path,
    *,
    run_id: str,
    model: Path,
    model_sha256: str,
    worker_command: Sequence[str],
    timeout: float = 900,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    execute=execute_worker,
) -> Handoff:
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
            *worker_command,
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ]
        (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (directory / "worker.log").open("w") as log:
            execute(command, log, timeout, cwd=cwd, env=None if env is None else dict(env))
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


def consume(handoff: Handoff, image: Path, sr_image: Path, output: Path) -> None:
    """Validate every row before atomically exposing one page's prediction."""
    manifest = Path(handoff.manifest).resolve()
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != handoff.manifest_sha256:
        raise ValueError("OMR job manifest changed")
    payload = json.loads(raw)
    if (
        payload.get("schema") != SCHEMA
        or payload.get("status") != "completed"
        or payload.get("run_id") != handoff.run_id
        or payload.get("model") != str(handoff.model)
        or payload.get("model_sha256") != handoff.model_sha256
        or digest(handoff.model) != handoff.model_sha256
    ):
        raise ValueError("OMR job handoff run/model/status mismatch")
    if digest(payload["worker_result"]) != payload["worker_result_sha256"]:
        raise ValueError("OMR job worker attestation changed")
    selected = []
    seen = set()
    for row in payload["rows"]:
        if row["image"] in seen:
            raise ValueError("duplicate page identity")
        seen.add(row["image"])
        prediction = Path(row["predictions"]).resolve()
        if not prediction.is_relative_to(manifest.parent / "predictions"):
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
        raise ValueError("page not uniquely bound to this OMR job")
    atomic_publish(Path(output), selected[0])
