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
    manifest = json.loads((root / "models/omr_dln/manifest.json").read_text())
    model = resolve_omr_dln_model_path(repository_root=root)
    handoff = job_phase.build(
        images,
        sr_outputs,
        directory,
        run_id=str(uuid.uuid4()),
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
