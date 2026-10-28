"""Research-only same-run OMR phase reuse; no production file or model changes.

SR exits, one production OMR subprocess processes the ordered pages and exits,
then disposable HOMR source workers consume hash-bound same-run predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MODULE = "tools.issue447.omr_reuse_poc"
SUPPORT = "src.pipeline.detection.current_support_worker"
OMR = "src.pipeline.detection.omr_dln_worker"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def build_manifest(images, sr_outputs, directory, execute=subprocess.run):
    directory.mkdir(parents=True, exist_ok=False)
    if len({p.stem for p in images}) != len(images):
        raise ValueError("PoC requires unique page stems")
    by_image = {Path(item["image"]).resolve(): item for item in sr_outputs}
    staged = directory / "sr"
    staged.mkdir()
    rows = []
    for image in images:
        image = image.resolve()
        item = by_image[image]
        sr = Path(item["sr_image"])
        if digest(sr) != item["sr_sha256"]:
            raise ValueError("fresh SR digest mismatch")
        (staged / image.name).symlink_to(sr.resolve())
        rows.append(
            {
                "image": str(image),
                "image_sha256": digest(image),
                "sr_image": str(sr.resolve()),
                "sr_sha256": item["sr_sha256"],
            }
        )
    command = [
        sys.executable,
        "-m",
        OMR,
        "--images",
        *map(str, images),
        "--output-dir",
        str(directory / "predictions"),
        "--pre-computed-sr",
        str(staged),
    ]
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (directory / "worker.log").open("w") as log:
        execute(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    for row in rows:
        prediction = directory / "predictions" / Path(row["image"]).stem / "predictions.json"
        # Force parse before publishing the completed handoff. Missing/partial results fail closed.
        if not isinstance(json.loads(prediction.read_text()), list):
            raise ValueError("invalid OMR predictions")
        row.update(predictions=str(prediction.resolve()), predictions_sha256=digest(prediction))
    manifest = directory / "completed.json"
    manifest.write_text(
        json.dumps(
            {"status": "completed", "scope": "fresh_same_run_omr_phase", "rows": rows}, indent=2
        )
        + "\n"
    )
    return manifest


def consume(manifest, image, sr_image, output):
    payload = json.loads(Path(manifest).read_text())
    if payload.get("status") != "completed" or payload.get("scope") != "fresh_same_run_omr_phase":
        raise ValueError("incomplete same-run OMR phase")
    rows = [r for r in payload["rows"] if Path(r["image"]) == image.resolve()]
    if len(rows) != 1:
        raise ValueError("OMR manifest image association mismatch")
    row = rows[0]
    if Path(row["sr_image"]) != sr_image.resolve():
        raise ValueError("OMR manifest SR path mismatch")
    for key, path in (
        ("image", image),
        ("sr", sr_image),
        ("predictions", Path(row["predictions"])),
    ):
        if digest(path) != row[key + "_sha256"]:
            raise ValueError(f"OMR manifest {key} digest mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    shutil.copyfile(row["predictions"], output)
    return row


def install(detector_class=None):
    if detector_class is None:
        from src.pipeline.detection.profile_sources_batch_sr import BatchSRProfileHybridDetector

        detector_class = BatchSRProfileHybridDetector
    original = detector_class._batch_sr_worker

    def batch(self, *, support_output):
        result = original(self, support_output=support_output)
        by_image, command, payload = result
        if payload.get("status") != "completed":
            raise RuntimeError("reuse requires completed SR phase")
        from src.pipeline.detection.model_selection import model_validation_mode

        if model_validation_mode(self.det_cfg) != "production":
            raise ValueError("PoC only supports production model selection")
        manifest = build_manifest(
            self.images, list(by_image.values()), support_output.parent / "issue447_omr_reuse"
        )
        os.environ["ISSUE447_OMR_MANIFEST"] = str(manifest.resolve())
        return result

    detector_class._batch_sr_worker = batch
    # Source CLI below rewrites only its nested support subprocess to this PoC.
    detector_class.source_worker_module = MODULE


def source_main():
    original = subprocess.run

    def child(command, *args, **kwargs):
        if isinstance(command, list) and SUPPORT in command:
            command = list(command)
            command[command.index(SUPPORT)] = MODULE
            command.insert(command.index("--request"), "--support")
        return original(command, *args, **kwargs)

    subprocess.run = child
    from src.pipeline.detection.maintained_source_page_worker import main

    return main()


def support_main():
    from src.pipeline.detection import current_support_worker as worker

    original = worker.run_with_logging
    request = json.loads(Path(sys.argv[sys.argv.index("--request") + 1]).read_text())
    image = Path(request["image"])
    sr_image = Path(request["precomputed_sr"]["sr_image"])
    substitutions = []

    def run(command, *args, **kwargs):
        if OMR not in command:
            return original(command, *args, **kwargs)
        destination = (
            Path(command[command.index("--output-dir") + 1]) / image.stem / "predictions.json"
        )
        consume(os.environ["ISSUE447_OMR_MANIFEST"], image, sr_image, destination)
        substitutions.append(command)
        return subprocess.CompletedProcess(command, 0)

    worker.run_with_logging = run
    code = worker.main()
    if code == 0:
        path = Path(sys.argv[sys.argv.index("--result") + 1])
        payload = json.loads(path.read_text())
        if len(substitutions) != 1:
            raise RuntimeError("expected exactly one OMR handoff")
        payload["commands"] = [
            (
                ["issue447-same-run-omr-handoff", os.environ["ISSUE447_OMR_MANIFEST"], str(image)]
                if c in substitutions
                else c
            )
            for c in payload["commands"]
        ]
        payload["memory_phase_boundaries"] = [
            "sr_batch_process_exited",
            "omr_batch_process_exited",
            "current_homr",
        ]
        payload["issue447_omr_manifest"] = os.environ["ISSUE447_OMR_MANIFEST"]
        path.write_text(json.dumps(payload, indent=2) + "\n")
    return code


if __name__ == "__main__":
    if "--help" in sys.argv:
        argparse.ArgumentParser(description=__doc__).print_help()
        raise SystemExit(0)
    if "--support" in sys.argv:
        sys.argv.remove("--support")
        raise SystemExit(support_main())
    raise SystemExit(source_main())
