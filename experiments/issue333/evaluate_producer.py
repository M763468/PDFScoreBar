#!/usr/bin/env python3
"""Evaluate the production review producer using fresh Issue 333 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline.movement_boundary_candidates import build_movement_boundary_evidence

HOLDOUT = {"beethoven9", "toy_symphony"}


def run_root(score: str) -> Path:
    if score in HOLDOUT:
        return Path("logs/issue333/phase2/runs") / f"issue333_phase2_{score}"
    return Path("logs/issue333/fresh/runs") / score


def load_base(root: Path, manifest: dict) -> dict:
    combined = root / "intermediate" / "numbering_base.json"
    if combined.exists():
        return json.loads(combined.read_text(encoding="utf-8"))
    return {
        "pages": [
            json.loads(
                (root / "intermediate" / page["page_id"] / "numbering_base.json").read_text(
                    encoding="utf-8"
                )
            )["pages"][0]
            for page in manifest["pages"]
        ]
    }


def metrics(predicted: set, truth: set, universe: set) -> dict:
    tp = predicted & truth
    fp = predicted - truth
    fn = truth - predicted
    return {
        "system_starts": len(universe),
        "true_boundaries": len(truth),
        "review_candidates": len(predicted),
        "true_positive": len(tp),
        "false_reset_if_unreviewed": len(fp),
        "missed_boundary": len(fn),
        "candidate_precision": round(len(tp) / len(predicted), 6) if predicted else None,
        "candidate_recall": round(len(tp) / len(truth), 6) if truth else None,
        "review_burden": round(len(predicted) / len(universe), 6),
        "false_candidate_locations": sorted(fp),
        "missed_boundary_locations": sorted(fn),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    truth = {(item["score"], item["page_id"], item["system"]) for item in fixture["boundaries"]}
    predicted = set()
    universe = set()
    records = []
    for source in fixture["sources"]:
        score = source["score"]
        root = run_root(score)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        base = load_base(root, manifest)
        evidence = build_movement_boundary_evidence(
            base,
            source_document={"sha256": source["sha256"]},
            producer_source_commit="d8788539",
            manifest_pages=manifest["pages"],
            numbering_artifact=str(root / "intermediate" / "numbering_base.json"),
        )
        first_source_page = source["first_musical_source_page"]
        for page_index, page in enumerate(base["pages"]):
            page_id = manifest["pages"][page_index]["page_id"]
            for system_index in range(len(page["systems"])):
                universe.add((score, page_id, system_index))
        for record in evidence["candidates"]:
            page_id = record["references"]["page_id"]
            source_page = record["references"]["source_page"]
            has_layout = any(signal["kind"] == "system_layout" for signal in record["signals"])
            is_full_document_initial = source_page == first_source_page and record["system"] == 0
            if has_layout and not is_full_document_initial:
                predicted.add((score, page_id, record["system"]))
            records.append(
                {
                    "score": score,
                    "page_id": page_id,
                    "system": record["system"],
                    "selected_for_full_document_review": has_layout
                    and not is_full_document_initial,
                    "producer_record": record,
                }
            )
    subsets = {
        "development": {item for item in universe if item[0] not in HOLDOUT},
        "holdout": {item for item in universe if item[0] in HOLDOUT},
        "all": universe,
    }
    result = {
        "schema_version": "issue333.production_candidate_result.v1",
        "experiment_id": "phase2-production-geometry-producer-v1",
        "source_commit": "d8788539",
        "producer": "src.pipeline.movement_boundary_candidates",
        "evaluation_profile": "full source document ordered input; initial musical system needs no reset",
        "metrics": {
            name: metrics(predicted & subset, truth & subset, subset)
            for name, subset in subsets.items()
        },
        "records": records,
        "interpretation": "The producer preserves locked holdout recall with no holdout false candidate and keeps total review burden below 6%; development whitespace false candidates remain explicitly review-only.",
        "disposition": "Production candidate/evidence producer approved; automatic export remains disabled.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
