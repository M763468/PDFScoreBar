#!/usr/bin/env python3
"""Fresh downstream replay for the Issue #372 combined detector counterfactual.

Runs only the downstream contract for the already-produced combined detector set:
late-raw x4 recovery + frozen pre-probe hybrid bands.

No detector/HOMR/SR/OMR/probe/CNN inference is run here. The combined final
barline set is retained input. Phase-A numbering, MMR, and final numbering are
freshly replayed with the same current downstream contract used by
run_fresh_downstream_semantic_replay.py.

A previously produced fresh downstream replay report is used only as the
reference for current_control / late_raw_x4 / accepted_d27 signatures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch

from experiments.issue372.reassess_final_numbering_values import (
    compare_number_values,
)
from experiments.issue372.run_fresh_downstream_semantic_replay import (
    EXPECTED_PAGES,
    _comparison,
    _extract_boxes,
    _find_page_file,
    _prepare_runtime,
    _run_variant_downstream,
)
from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _load_json,
    _write_json,
)
from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from tools.issue120 import eval_full68_from_intermediates as full68_eval


def _reference_page_map(
    report: Mapping[str, Any],
    label: str,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    variants = report.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("reference replay lacks variants")
    variant = variants.get(label)
    if not isinstance(variant, Mapping) or not isinstance(variant.get("per_page"), list):
        raise ValueError(f"reference replay lacks variant {label}")
    result = {}
    for row in variant["per_page"]:
        if not isinstance(row, Mapping):
            continue
        result[(str(row["score"]), str(row["page"]))] = row
    if len(result) != EXPECTED_PAGES:
        raise RuntimeError(
            f"reference {label}: expected {EXPECTED_PAGES} pages, got {len(result)}"
        )
    return result


def _combined_barlines(
    probe_root: Path,
) -> tuple[dict[tuple[str, str], list[tuple[int, int, int, int]]], int]:
    rows: dict[tuple[str, str], list[tuple[int, int, int, int]]] = {}
    total = 0
    for score, pages in full68_eval.SCORES.items():
        for page in pages:
            path = _find_page_file(
                probe_root,
                score,
                page,
                "pipeline2_no_peak_filtered_cnn.json",
            )
            boxes = _extract_boxes(_load_json(path))
            rows[(score, page)] = boxes
            total += len(boxes)
    if len(rows) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} combined pages, got {len(rows)}")
    return rows, total


def _number_value_signature(row: Mapping[str, Any]) -> dict[str, Any]:
    local = row["local_logical"]
    continued = row["continued_logical"]
    return {
        "local_system_count": local["system_count"],
        "local_system_measure_counts": [
            system["measure_count"] for system in local["systems"]
        ],
        "local_number_sequences": [
            system["numbers"] for system in local["systems"]
        ],
        "continued_system_count": continued["system_count"],
        "continued_system_measure_counts": [
            system["measure_count"] for system in continued["systems"]
        ],
        "continued_number_sequences": [
            system["numbers"] for system in continued["systems"]
        ],
        "continued_start_number": row["continued_start_number"],
        "continued_next_number": row["continued_next_number"],
        "mmr_overrides": row["mmr_overrides"],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    combined_report_path = args.combined_report.resolve()
    reference_replay_path = args.reference_replay.resolve()
    x4_run_root = args.x4_run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    image_root = args.image_root.resolve()
    model_path = args.mmr_model.resolve()
    output_root = args.output_root.resolve()

    for required in (
        combined_report_path,
        reference_replay_path,
        x4_run_root,
        issue43_repo_root,
        image_root,
        model_path,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")

    combined_report = _load_json(combined_report_path)
    reference = _load_json(reference_replay_path)
    if not isinstance(combined_report, Mapping) or not isinstance(reference, Mapping):
        raise ValueError("reports must be JSON objects")

    probe_root = Path(str(combined_report["aggregate_probe"]))
    if not probe_root.is_dir():
        raise FileNotFoundError(probe_root)

    barlines, barline_total = _combined_barlines(probe_root)
    runtime = _prepare_runtime(
        x4_run_root=x4_run_root,
        issue43_repo_root=issue43_repo_root,
        image_root=image_root,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Fresh downstream replay requires CUDA for production evidence")
    classifier = MMRClassifier(model_path, device)
    ocr_engine = MMROCREngine(enable_rotation_tta=False)

    output_root.mkdir(parents=True, exist_ok=True)
    print("=== downstream variant: combined_late_raw_frozen_bands ===", flush=True)
    combined = _run_variant_downstream(
        label="combined_late_raw_frozen_bands",
        barlines=barlines,
        runtime=runtime,
        output_root=output_root,
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=ocr_engine,
        mmr_threshold=float(args.mmr_threshold),
        rescue_threshold=float(args.mmr_rescue_threshold),
    )

    refs = {
        label: _reference_page_map(reference, label)
        for label in ("current_control", "late_raw_x4", "accepted_d27")
    }
    comparisons = {
        "combined_vs_current": _comparison(refs["current_control"], combined),
        "combined_vs_late": _comparison(refs["late_raw_x4"], combined),
        "combined_vs_d27": _comparison(refs["accepted_d27"], combined),
    }
    number_values = {
        "combined_vs_current": compare_number_values(refs["current_control"], combined),
        "combined_vs_late": compare_number_values(refs["late_raw_x4"], combined),
        "combined_vs_d27": compare_number_values(refs["accepted_d27"], combined),
    }

    target = ("Shostakovich-Sym5-Va", "page_021")
    combined_target = combined[target]
    target_refs = {
        label: refs[label][target]
        for label in ("current_control", "late_raw_x4", "accepted_d27")
    }

    target_payload = {
        "combined": _number_value_signature(combined_target),
        "references": {
            label: _number_value_signature(row)
            for label, row in target_refs.items()
        },
    }

    per_page = [
        {"score": score, "page": page, **row}
        for (score, page), row in sorted(combined.items())
    ]
    result = {
        "schema_version": "issue372.combined_downstream_semantic_replay.v1",
        "contract": {
            "detector_rerun": False,
            "homr_sr_omr_rerun": False,
            "probe_rerun": False,
            "cnn_rerun": False,
            "combined_detector_source": str(probe_root),
            "phase_a_numbering_fresh": True,
            "mmr_inference_fresh": True,
            "final_numbering_fresh": True,
            "reference_replay": str(reference_replay_path),
            "blocking_number_value_fields": [
                "system count",
                "per-system physical measure count",
                "serialized measure-number sequence",
                "continued start/next number state",
                "MMR skip overrides",
            ],
        },
        "variant_summary": {
            "barline_count": barline_total,
            "mmr_override_count": sum(
                len(row["mmr_overrides"]) for row in combined.values()
            ),
            "page_count": len(combined),
        },
        "comparisons": comparisons,
        "number_value_comparisons": number_values,
        "page021": target_payload,
        "variants": {
            "combined_late_raw_frozen_bands": {
                "barline_count": barline_total,
                "final_selected_page_count": len(combined),
                "per_page": per_page,
            }
        },
    }

    report_path = output_root / "combined_downstream_semantic_replay.json"
    _write_json(report_path, result)

    print("=== Issue #372 combined downstream semantic replay ===")
    print(f"barline_count={barline_total}")
    for name, comparison in number_values.items():
        print(
            f"{name}: number_value_match={comparison['number_value_match']} "
            f"changed_pages={comparison['changed_page_count']}"
        )
    print("\n=== Shostakovich-Sym5-Va/page_021 ===")
    for label in ("combined", "current_control", "late_raw_x4", "accepted_d27"):
        payload = (
            target_payload["combined"]
            if label == "combined"
            else target_payload["references"][label]
        )
        print(
            f"{label}: measures={payload['continued_system_measure_counts']} "
            f"start={payload['continued_start_number']} "
            f"next={payload['continued_next_number']} "
            f"numbers={payload['continued_number_sequences']}"
        )
    print(f"OUTPUT={report_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-report", type=Path, required=True)
    parser.add_argument("--reference-replay", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument(
        "--mmr-model",
        type=Path,
        default=ROOT / "tools/mmr_training/models/mmr_classifier_best.pth",
    )
    parser.add_argument("--mmr-threshold", type=float, default=0.5)
    parser.add_argument("--mmr-rescue-threshold", type=float, default=0.1)
    parser.add_argument("--output-root", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
