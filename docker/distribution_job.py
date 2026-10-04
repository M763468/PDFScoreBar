"""Thin local command adapter for the existing v1 PDF engine."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.pipeline.engine_contract import JobRequest, JobStatus, OutputProfile
from src.pipeline.engine_executor import PipelineJobExecutor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pages", type=int, nargs="+")
    args = parser.parse_args()
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
    print(result.to_json(include_debug_context=True))
    output = args.output / result.job_id
    if output.is_dir():
        (output / "result.json").write_text(result.to_json() + "\n", encoding="utf-8")
    return 0 if result.status in {JobStatus.SUCCEEDED, JobStatus.REVIEW_REQUIRED} else 1


if __name__ == "__main__":
    raise SystemExit(main())
