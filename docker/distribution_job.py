"""Thin local command adapter for the existing v1 PDF engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from src.pipeline.engine_contract import JobRequest, JobStatus, OutputProfile
from src.pipeline.engine_executor import PipelineJobExecutor


def prepare_local_review(package: Path) -> str:
    """Bind a local user review to retained artifacts, preserving engine originals."""
    package = package.resolve()
    handoff = package / "review/manual_correction_input.json"
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    job_id = payload["source_job_id"]
    if not isinstance(job_id, str) or Path(job_id).name != job_id or job_id in {".", ".."}:
        raise ValueError("Invalid source job identity")
    retained = package / ".engine-retained"
    original = retained / "runs" / job_id / "manifest.json"
    if not original.resolve().is_relative_to(package) or not original.is_file():
        raise ValueError("Local review requires its retained engine manifest")
    raw = original.read_bytes()
    source = json.loads(raw)
    old_run = Path(source["run_dir"])
    if (
        not old_run.is_absolute()
        or old_run.name != job_id
        or old_run.parent.name != "runs"
        or old_run.parent.parent.name != ".engine-work"
    ):
        raise ValueError("Unexpected retained engine work path")
    old_root = str(old_run.parent.parent)

    # Rewrite only absolute paths rooted at the former work directory. Every
    # numerical/config value and the original retained manifest remain intact.
    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str) and (value == old_root or value.startswith(old_root + "/")):
            return str(retained) + value[len(old_root) :]
        return value

    local = original.with_name("local_manifest.json")
    normalized = relocate(source)
    normalized["local_distribution_source"] = {
        "original_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "original_manifest": "manifest.json",
        "source_job_id": job_id,
    }
    local.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    payload["source_manifest"] = "../" + local.relative_to(package).as_posix()
    handoff.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
    result_path = package / "result.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for artifact in result["artifacts"]:
            if artifact["reference"] == "review/manual_correction_input.json":
                artifact["sha256"] = sha
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--prepare-review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pages", type=int, nargs="+")
    args = parser.parse_args()
    if args.prepare_review:
        prepare_local_review(args.prepare_review)
        return 0
    if args.pdf is None or args.output is None:
        parser.error("pdf and --output are required for a PDF job")
    pdf = args.pdf.resolve()
    overrides = {"pages": args.pages} if args.pages else {}
    executor = PipelineJobExecutor(
        input_root=pdf.parent,
        artifact_root=args.output,
        source_commit=os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT"),
    )
    result = executor(
        JobRequest(
            input={"kind": "local_path", "reference": pdf.name},
            output_profile=OutputProfile.REVIEW,
            config_overrides=overrides,
        )
    )
    output = args.output / result.job_id
    if result.status in {JobStatus.SUCCEEDED, JobStatus.REVIEW_REQUIRED}:
        sha = prepare_local_review(output)
        result = replace(
            result,
            artifacts=tuple(
                replace(artifact, sha256=sha)
                if artifact.reference == "review/manual_correction_input.json"
                else artifact
                for artifact in result.artifacts
            ),
        )
    print(result.to_json(include_debug_context=True))
    if output.is_dir():
        (output / "result.json").write_text(result.to_json() + "\n", encoding="utf-8")
    return 0 if result.status in {JobStatus.SUCCEEDED, JobStatus.REVIEW_REQUIRED} else 1


if __name__ == "__main__":
    raise SystemExit(main())
