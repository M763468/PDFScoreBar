#!/usr/bin/env python3
"""Evaluate frozen and union-geometry Issue #333 candidates on complete documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.pipeline.movement_boundary_candidates import build_movement_boundary_evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_run(root: Path, musical_source_pages: list[int]) -> tuple[dict, list[dict]]:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest["pages"]) != len(musical_source_pages):
        raise ValueError(f"page selection mismatch: {root}")
    pages = []
    for manifest_page in manifest["pages"]:
        artifact = root / "intermediate" / manifest_page["page_id"] / "numbering_base.json"
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        if len(payload["pages"]) != 1:
            raise ValueError(f"expected one page in {artifact}")
        pages.append(payload["pages"][0])
    contract_path = root / "intermediate" / "detector_input_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if not (
        contract["mode"] == "fresh_upstream"
        and contract["fresh_upstream_authoritative"] is True
        and contract["detector_route"] == "dense_full_pipeline"
        and contract["homr_profile"] == "stage_e_verified"
        and contract["sr_scale"] == 4
    ):
        raise ValueError(f"non-canonical detector contract: {root}")
    provenance = {
        "root": str(root),
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "detector_input_contract": str(contract_path),
        "detector_input_contract_sha256": _sha256(contract_path),
        "source_commit": manifest.get("source_commit"),
        "config": manifest["config"],
    }
    return {"pages": pages}, [provenance, manifest["pages"]]


def _union_numbering(numbering: dict) -> dict:
    result = deepcopy(numbering)
    for page in result["pages"]:
        for system in page["systems"]:
            boxes = [staff["bbox"] for staff in system["staves"]]
            system["staves"] = [
                {
                    "bbox": [
                        min(box[0] for box in boxes),
                        min(box[1] for box in boxes),
                        max(box[2] for box in boxes),
                        max(box[3] for box in boxes),
                    ]
                }
            ]
    return result


def _metrics(
    records: list[dict],
    truth: set[tuple[int, int]],
    page_count: int,
    musical_page_count: int,
    systems: int,
) -> dict[str, Any]:
    predicted = {
        (record["page"], record["system"])
        for record in records
        if record["state"] == "ambiguous_review_required"
    }
    true_positive = predicted & truth
    false_candidates = predicted - truth
    missed = truth - predicted
    return {
        "candidate_count": len(predicted),
        "true_positive": len(true_positive),
        "false_candidate": len(false_candidates),
        "missed_boundary": len(missed),
        "recall": round(len(true_positive) / len(truth), 6) if truth else None,
        "candidate_precision": (
            round(len(true_positive) / len(predicted), 6) if predicted else None
        ),
        "candidates_per_source_page": round(len(predicted) / page_count, 6),
        "candidates_per_musical_page": round(len(predicted) / musical_page_count, 6),
        "candidates_per_system": round(len(predicted) / systems, 6),
        "true_positive_locations": sorted([list(item) for item in true_positive]),
        "false_candidate_locations": sorted([list(item) for item in false_candidates]),
        "missed_boundary_locations": sorted([list(item) for item in missed]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    gt = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    sources = []
    aggregate: dict[str, Any] = {
        "total_source_pages": 0,
        "musical_pages": 0,
        "systems": 0,
        "true_boundaries": 0,
    }
    aggregate_predictions = {"first_staff": [], "union": []}
    aggregate_truth: set[tuple[int, int, int]] = set()
    for score_index, source in enumerate(corpus["sources"]):
        score = source["score"]
        run = next(item for item in runs["runs"] if item["score"] == score)
        numbering, run_data = _load_run(Path(run["root"]), source["musical_source_pages"])
        provenance, manifest_pages = run_data
        systems = sum(len(page["systems"]) for page in numbering["pages"])
        truth = {
            (item["page"], item["system"]) for item in gt["boundaries"] if item["score"] == score
        }
        source_document = {"sha256": source["sha256"], "page_order": "ordered_input"}
        variants = {}
        for name, payload in (
            ("first_staff", numbering),
            ("union", _union_numbering(numbering)),
        ):
            evidence = build_movement_boundary_evidence(
                payload,
                source_document=source_document,
                producer_source_commit=runs["producer_source_commit"],
                manifest_pages=manifest_pages,
            )
            variants[name] = _metrics(
                evidence["candidates"],
                truth,
                source["page_count"],
                len(source["musical_source_pages"]),
                systems,
            )
            aggregate_predictions[name].extend(
                (score_index, record["page"], record["system"])
                for record in evidence["candidates"]
                if record["state"] == "ambiguous_review_required"
            )
        aggregate_truth.update((score_index, page, system) for page, system in truth)
        multi_staff = [
            [page_index, system_index, len(system["staves"])]
            for page_index, page in enumerate(numbering["pages"])
            for system_index, system in enumerate(page["systems"])
            if len(system["staves"]) > 1
        ]
        sources.append(
            {
                "score": score,
                "source_pages": source["page_count"],
                "musical_pages": len(source["musical_source_pages"]),
                "ordered_page_to_source_page": source["musical_source_pages"],
                "systems": systems,
                "true_boundaries": len(truth),
                "multi_staff_systems": multi_staff,
                "artifact_provenance": provenance,
                "variants": variants,
            }
        )
        aggregate["total_source_pages"] += source["page_count"]
        aggregate["musical_pages"] += len(source["musical_source_pages"])
        aggregate["systems"] += systems
        aggregate["true_boundaries"] += len(truth)
    for name, predictions in aggregate_predictions.items():
        predicted = set(predictions)
        tp = predicted & aggregate_truth
        fp = predicted - aggregate_truth
        fn = aggregate_truth - predicted
        aggregate[name] = {
            "candidate_count": len(predicted),
            "true_positive": len(tp),
            "false_candidate": len(fp),
            "missed_boundary": len(fn),
            "recall": round(len(tp) / len(aggregate_truth), 6),
            "candidate_precision": round(len(tp) / len(predicted), 6),
            "candidates_per_source_page": round(
                len(predicted) / aggregate["total_source_pages"], 6
            ),
            "candidates_per_musical_page": round(len(predicted) / aggregate["musical_pages"], 6),
            "candidates_per_system": round(len(predicted) / aggregate["systems"], 6),
            "true_positive_locations": sorted([list(item) for item in tp]),
            "false_candidate_locations": sorted([list(item) for item in fp]),
            "missed_boundary_locations": sorted([list(item) for item in fn]),
        }
    result = {
        "schema_version": "issue333.phase25_full_document_result.v1",
        "producer_source_commit": runs["producer_source_commit"],
        "ground_truth_sha256": _sha256(args.ground_truth),
        "corpus_sha256": _sha256(args.corpus),
        "coordinate_system": gt["coordinate_system"],
        "sources": sources,
        "aggregate": aggregate,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
