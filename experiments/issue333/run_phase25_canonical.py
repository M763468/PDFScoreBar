#!/usr/bin/env python3
"""Materialize and optionally execute canonical Phase-A runs for Issue #333."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from src.pipeline.core.config import load_yaml, write_yaml
from src.pipeline.main import run_pipeline

PDF_ROOTS = (Path("/source-evaluation2"), Path("/source-evaluation"), Path("/source-training"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    baseline_path = Path("configs/dense_full_pipeline.yaml")
    corpus_path = Path("experiments/issue333/corpus.json")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    source = next(item for item in corpus["sources"] if item["score"] == args.score)
    matches = [
        match for root in PDF_ROOTS if root.exists() for match in root.rglob(source["pdf_filename"])
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one mounted source PDF, found {matches}")
    pdf_path = matches[0]
    if _sha256(pdf_path) != source["sha256"]:
        raise ValueError("source PDF digest mismatch")

    config = deepcopy(load_yaml(baseline_path))
    run_id = f"canonical_musical_{args.score}"
    output_root = Path("logs/issue333/phase25/canonical")
    config["run"] = {"run_id": run_id, "output_root": str(output_root)}
    config["inputs"]["pdf_path"] = str(pdf_path)
    config["inputs"]["pdf_to_images"] = {
        "dpi": 300.0,
        "pages": ",".join(str(index + 1) for index in source["musical_source_pages"]),
        "prefix": "page",
        "format": "png",
        "image_glob": "page_*.png",
    }
    config["steps"]["pdf_to_images"] = True
    config["steps"]["mmr_overrides"] = False
    config["steps"]["apply_measure_overrides"] = False
    config["steps"]["overlay"] = False
    config["detection"]["hybrid_output_root"] = str(output_root / run_id / "hybrid_output")
    generated_dir = Path("logs/issue333/phase25/generated_configs")
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_path = generated_dir / f"{args.score}.yaml"
    write_yaml(generated_path, config)
    provenance = {
        "schema_version": "issue333.canonical_run_request.v1",
        "score": args.score,
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": source["sha256"],
        "source_page_count": source["page_count"],
        "musical_source_pages": source["musical_source_pages"],
        "page_selection_semantics": "one-based physical PDF pages passed to normalise_pages; rendered stems retain the physical source index",
        "baseline_config": str(baseline_path),
        "baseline_config_sha256": _sha256(baseline_path),
        "generated_config": str(generated_path),
        "generated_config_sha256": _sha256(generated_path),
        "detector_route": config["detection"]["detector_route"],
        "homr_profile": config["detection"]["homr_profile"],
        "sr_scale": config["detection"]["sr_scale"],
        "cnn_model_manifest": config["detection"]["cnn_model_manifest"],
        "phase_a_only": True,
    }
    (generated_dir / f"{args.score}.provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if args.execute:
        run_pipeline(generated_path)


if __name__ == "__main__":
    main()
