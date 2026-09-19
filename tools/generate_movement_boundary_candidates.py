#!/usr/bin/env python3
"""Generate review-only movement-boundary evidence from numbering geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.pipeline.movement_boundary_candidates import build_movement_boundary_evidence
from src.pipeline.utils.io import load_json, write_json


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_manifest_source_hash(manifest: dict, source_sha256: str) -> None:
    hashes = set()
    for page in manifest.get("pages", []):
        reference = page.get("source_reference") if isinstance(page, dict) else None
        if not isinstance(reference, dict) or reference.get("kind") != "direct_pdf_render":
            continue
        document = reference.get("source_document")
        digest = document.get("sha256") if isinstance(document, dict) else None
        if not isinstance(digest, str):
            raise ValueError(
                "direct_pdf_render source_reference must contain source_document.sha256"
            )
        hashes.add(digest.lower())
    if hashes and (hashes != {source_sha256.lower()}):
        raise ValueError(
            "--source-pdf-sha256 does not match verified direct_pdf_render manifest provenance"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbering-base", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-pdf-sha256", required=True)
    parser.add_argument("--producer-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    manifest_pages = manifest.get("pages") if isinstance(manifest, dict) else None
    if not isinstance(manifest_pages, list):
        raise ValueError("manifest must contain a pages list")
    source_sha256 = args.source_pdf_sha256.lower()
    _validate_manifest_source_hash(manifest, source_sha256)
    source_document = {
        "sha256": source_sha256,
        "page_order": "ordered_pipeline_input",
        "input_manifest": str(args.manifest),
        "input_manifest_sha256": sha256(args.manifest),
    }
    evidence = build_movement_boundary_evidence(
        load_json(args.numbering_base),
        source_document=source_document,
        producer_source_commit=args.producer_source_commit,
        manifest_pages=manifest_pages,
        numbering_artifact=str(args.numbering_base),
    )
    write_json(args.output, evidence)
    print(json.dumps({"output": str(args.output), "records": len(evidence["candidates"])}))


if __name__ == "__main__":
    main()
