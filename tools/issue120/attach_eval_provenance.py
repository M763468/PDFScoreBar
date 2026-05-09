#!/usr/bin/env python3
"""Attach intermediate provenance metadata to an Issue #120 evaluation contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def default_provenance(results_dir: str) -> dict[str, Any]:
    return {
        "schema_version": "issue120.intermediate_provenance.v1",
        "status": "default_unverified",
        "results_dir": results_dir,
        "evaluated_stage": "post_cnn_scoring_detector_intermediate",
        "evaluated_files": {
            "scored": "pipeline2_no_peak_scored.json",
            "candidates": "pipeline2_no_peak_candidates.json",
        },
        "pipeline_stage_boundary": {
            "included_before_this_intermediate": [
                "initial OMR/HOMR pass",
                "optional SR image generation",
                "OMR/HOMR pass on SR image",
                "optional OMR-DLN or other detector outputs used by the run",
                "hybrid consensus / seed preparation",
                "probe scan candidate generation",
                "CNN scoring of candidates",
            ],
            "not_validated_by_this_evaluation": [
                "whether the upstream OMR/HOMR/SR intermediates were regenerated from the current code",
                "whether the seed-generation script matches the current production pipeline",
                "downstream measure numbering quality unless a measure summary is attached",
            ],
        },
        "generation_command": None,
        "generation_commit": None,
        "source_artifact": None,
        "notes": [
            "This provenance block was auto-generated because no --provenance-json was supplied.",
            "Treat detector metrics as a validation of the saved post-CNN scoring intermediates, not as full pipeline reproduction.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory containing evaluation_contract.json.",
    )
    parser.add_argument(
        "--results-dir",
        required=True,
        help="Intermediate result root used by the evaluator.",
    )
    parser.add_argument(
        "--provenance-json",
        type=Path,
        default=None,
        help="Optional provenance JSON supplied by the local experiment run.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    contract_path = output_dir / "evaluation_contract.json"
    if not contract_path.exists():
        raise SystemExit(f"evaluation_contract.json not found: {contract_path}")

    contract = load_json(contract_path)
    if args.provenance_json is not None:
        if not args.provenance_json.exists():
            raise SystemExit(f"provenance JSON not found: {args.provenance_json}")
        provenance = load_json(args.provenance_json)
    else:
        provenance = default_provenance(args.results_dir)

    contract["intermediate_provenance"] = provenance
    write_json(contract_path, contract)
    write_json(output_dir / "intermediate_provenance.json", provenance)
    print(f"Attached intermediate provenance: {contract_path}")


if __name__ == "__main__":
    main()
