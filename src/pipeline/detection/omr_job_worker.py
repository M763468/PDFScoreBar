"""One OMR-DLN model/predictor lifetime for an ordered job; hash-bound attestation.

Started only by :func:`src.pipeline.detection.omr_job.build`. Loads the verified
production checkpoint explicitly on CUDA (no CPU fallback) and runs the existing
``omr_dln_worker.run`` loop once for every ordered page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from src.pipeline.detection.omr_job import SCHEMA, atomic_publish, digest, prediction_bytes


def run(request_path, result_path, *, infer=None):
    raw = Path(request_path).read_bytes()
    request = json.loads(raw)
    if request.get("schema") != SCHEMA:
        raise ValueError("unsupported OMR job protocol")
    rows = request["rows"]
    images = [Path(row["image"]).resolve() for row in rows]
    if not images or len({p.stem for p in images}) != len(images):
        raise ValueError("ordered pages require unique stems")
    model = Path(request["model"])
    output = Path(request["output_dir"])
    if output.exists() or Path(result_path).exists():
        raise FileExistsError("OMR job worker output must be fresh")

    def verify():
        if digest(model) != request["model_sha256"]:
            raise ValueError("worker model identity mismatch")
        for row, image in zip(rows, images):
            sr = Path(row["sr_image"]).resolve()
            staged = Path(request["sr_base"]) / (image.stem + ".png")
            if (
                staged.resolve() != sr
                or digest(image) != row["image_sha256"]
                or digest(sr) != row["sr_sha256"]
            ):
                raise ValueError("worker input/SR identity mismatch")

    runtime = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "image_id": os.environ.get("PDFSCORE_DOCKER_IMAGE_ID"),
        "pid": os.getpid(),
        "python": sys.executable,
        "device": "cuda",
    }
    if any(runtime.get(key) != value for key, value in request["runtime"].items()):
        raise ValueError("worker runtime identity mismatch")
    verify()
    if infer is None:
        from src.pipeline.detection.omr_dln_worker import run as infer
    outputs = infer(
        images,
        output_dir=output,
        precomputed_sr=Path(request["sr_base"]),
        model_path=model,
        device_name="cuda",
    )
    verify()
    expected = [output / image.stem / "predictions.json" for image in images]
    if outputs != expected:
        raise ValueError("worker output order/association mismatch")
    results = []
    for row, prediction in zip(rows, expected):
        data = prediction_bytes(prediction)
        results.append(
            {
                **row,
                "predictions": str(prediction),
                "predictions_sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    payload = {
        "schema": SCHEMA,
        "status": "completed",
        "run_id": request["run_id"],
        "request_sha256": hashlib.sha256(raw).hexdigest(),
        "model_sha256": request["model_sha256"],
        "rows": results,
        "runtime": runtime,
    }
    atomic_publish(result_path, (json.dumps(payload, indent=2) + "\n").encode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.request, args.result)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
