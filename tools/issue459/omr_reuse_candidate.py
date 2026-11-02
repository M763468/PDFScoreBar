"""Research integration of the attested job protocol; production selects none of this."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import uuid
from pathlib import Path

from tools.issue447 import omr_reuse_poc as shim
from tools.issue459 import job_phase

MODULE = "tools.issue459.omr_reuse_candidate"


def build_manifest(images, sr_outputs, directory):
    from src.common.model_artifacts import resolve_omr_dln_model_path

    os.environ.pop("ISSUE459_HANDOFF", None)
    os.environ.pop("ISSUE447_OMR_MANIFEST", None)
    root = Path(__file__).resolve().parents[2]
    model_manifest = root / "models/omr_dln/manifest.json"
    if job_phase.digest(model_manifest) != os.environ["ISSUE459_MODEL_MANIFEST_SHA256"]:
        raise ValueError("model selection changed during SR")
    manifest = json.loads(model_manifest.read_text())
    model = resolve_omr_dln_model_path(repository_root=root)
    handoff = job_phase.build(
        images,
        sr_outputs,
        directory,
        run_id=os.environ["ISSUE459_RUN_ID"],
        model=model,
        model_sha256=manifest["sha256"],
    )
    os.environ["ISSUE459_HANDOFF"] = json.dumps(dataclasses.asdict(handoff), default=str)
    return handoff.manifest


def consume(manifest, image, sr_image, output):
    payload = json.loads(os.environ["ISSUE459_HANDOFF"])
    payload["manifest"] = Path(payload["manifest"])
    payload["model"] = Path(payload["model"])
    handoff = job_phase.Handoff(**payload)
    if Path(manifest).resolve() != handoff.manifest.resolve():
        raise ValueError("unexpected job manifest")
    return job_phase.consume(handoff, image, sr_image, output)


def configure():
    shim.MODULE = MODULE
    shim.build_manifest = build_manifest
    shim.consume = consume


def install(detector_class=None):
    if detector_class is None:
        from src.pipeline.detection.maintained_profile_hybrid import (
            BatchSRVerifiedProfileHybridDetector,
        )

        detector_class = BatchSRVerifiedProfileHybridDetector
    original = detector_class._batch_sr_worker

    def bound_sr(self, *, support_output):
        run_id = str(uuid.uuid4())
        identities = {Path(p).resolve(): job_phase.digest(p) for p in self.images}
        root = Path(__file__).resolve().parents[2]
        model_manifest_digest = job_phase.digest(root / "models/omr_dln/manifest.json")
        os.environ["ISSUE459_RUN_ID"] = run_id
        os.environ["ISSUE459_MODEL_MANIFEST_SHA256"] = model_manifest_digest
        job_phase.atomic_publish(
            support_output.parent / "issue459_sr_inputs.json",
            (
                json.dumps(
                    {
                        "run_id": run_id,
                        "model_manifest_sha256": model_manifest_digest,
                        "inputs": {str(p): sha for p, sha in identities.items()},
                    },
                    indent=2,
                )
                + "\n"
            ).encode(),
        )
        by_image, command, payload = original(self, support_output=support_output)
        sr_request_path = support_output / "_sr_batch/request.json"
        sr_request = json.loads(sr_request_path.read_text())
        expected_outputs = {
            Path(item["image"]).resolve(): Path(item["output"]).resolve()
            for item in sr_request["items"]
        }
        if set(expected_outputs) != set(identities):
            raise ValueError("SR request page association mismatch")
        for image, expected in identities.items():
            if job_phase.digest(image) != expected:
                raise ValueError("source changed during SR")
            sr_image = Path(by_image[image]["sr_image"]).resolve()
            if sr_image != expected_outputs[image] or not sr_image.is_relative_to(
                support_output.resolve()
            ):
                raise ValueError("SR result is not the fresh job output")
            by_image[image] = {**by_image[image], "image_sha256": expected, "job_run_id": run_id}
        return by_image, command, payload

    detector_class._batch_sr_worker = bound_sr
    configure()
    shim.install(detector_class)


def main():
    if "--help" in sys.argv:
        argparse.ArgumentParser(description=__doc__).print_help()
        return 0
    configure()
    if "--support" in sys.argv:
        sys.argv.remove("--support")
        code = shim.support_main()
        if code == 0:
            path = Path(sys.argv[sys.argv.index("--result") + 1])
            payload = json.loads(path.read_text())
            payload["omr_job_handoff"] = json.loads(os.environ["ISSUE459_HANDOFF"])
            path.write_text(json.dumps(payload, indent=2) + "\n")
        return code
    return shim.source_main()


if __name__ == "__main__":
    raise SystemExit(main())
