#!/usr/bin/env python3
"""Trace all focused missing barlines through the authoritative fresh route."""

from __future__ import annotations

import argparse
import csv
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import (
    Box,
    artifact_record,
    normalize_box,
    target_metrics,
    validate_fresh_contract_payload,
    write_json,
)
from tools.issue252.trace_prokofiev_probe_boundary import build_report as build_target_trace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = PROJECT_ROOT / "configs" / "dense_full_pipeline.yaml"
SOURCE_NAMES = ("fresh_baseline", "current_sr", "current_omr")


def _is_box(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and len(value) >= 4
    )


def _load_boxes(path: Path) -> list[Box]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _load_scored(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected scored list: {path}")
    result = []
    for item in payload:
        if not isinstance(item, Mapping) or not _is_box(item.get("bbox")):
            continue
        result.append({"bbox": normalize_box(item["bbox"]), "score": item.get("score")})
    return result


def _missing_accepted_boxes(
    accepted: Sequence[Box], current: Sequence[Box], *, accepted_iou: float
) -> list[Box]:
    return [
        box
        for box in accepted
        if not target_metrics(box, current, accepted_iou=accepted_iou)["accepted"]
    ]


def _resolve_targets(
    *,
    accepted_boxes: Sequence[Box],
    current_boxes: Sequence[Box],
    metadata: Sequence[Mapping[str, Any]],
    accepted_iou: float,
) -> list[dict[str, Any]]:
    missing = _missing_accepted_boxes(
        accepted_boxes, current_boxes, accepted_iou=accepted_iou
    )
    if not metadata:
        return [
            {
                "id": f"missing_{index:03d}",
                "accepted_bbox": list(box),
                "status": "missing_from_current_final",
            }
            for index, box in enumerate(missing, 1)
        ]
    result = []
    for index, item in enumerate(metadata, 1):
        if not _is_box(item.get("accepted_bbox")):
            raise ValueError(f"Target metadata row {index} lacks accepted_bbox")
        box = normalize_box(item["accepted_bbox"])
        if not target_metrics(box, accepted_boxes, accepted_iou=accepted_iou)["accepted"]:
            raise ValueError(f"Target is absent from accepted reference: {list(box)}")
        row = dict(item)
        row["id"] = str(item.get("id") or f"target_{index:03d}")
        row["accepted_bbox"] = list(box)
        row["status"] = (
            "already_present_in_current_final"
            if target_metrics(box, current_boxes, accepted_iou=accepted_iou)["accepted"]
            else "missing_from_current_final"
        )
        result.append(row)
    return result


def _first_loss_boundary(
    *,
    source_trace: Mapping[str, Mapping[str, Any]],
    probe_trace: Mapping[str, Any],
    cnn_scored: Mapping[str, Any],
    cnn_accepted: Mapping[str, Any],
    accepted_final: bool,
) -> str:
    if accepted_final:
        return "already_accepted_final"
    if not any(source_trace[name]["accepted"] for name in SOURCE_NAMES):
        return "baseline_homr"
    if not source_trace["hybrid"]["accepted"]:
        return "hybrid_consensus"
    if not probe_trace.get("row_bands"):
        return "row_band_construction"
    for key, boundary in (
        ("raw", "raw_probe_generation"),
        ("size_filtered", "size_filter"),
        ("heuristic_filtered", "candidate_filter"),
        ("trimmed", "trim"),
        ("final", "probe_final_set"),
    ):
        if not probe_trace[key]["accepted"]:
            return boundary
    if not cnn_scored["accepted"]:
        return "cnn_scoring_input"
    if not cnn_accepted["accepted"]:
        return "cnn_filtering"
    return "final_detector_merge"


def _nearest(reference: Box, boxes: Sequence[Box]) -> Box:
    if not boxes:
        return reference
    rx = (reference[0] + reference[2]) / 2
    ry = (reference[1] + reference[3]) / 2
    return min(
        boxes,
        key=lambda box: (
            abs(rx - (box[0] + box[2]) / 2),
            abs(ry - (box[1] + box[3]) / 2),
        ),
    )


def _scored_metrics(reference: Box, records: Sequence[Mapping[str, Any]], iou: float):
    metrics = target_metrics(
        reference, [normalize_box(item["bbox"]) for item in records], accepted_iou=iou
    )
    best = metrics.get("best")
    metrics["best_score"] = None
    if isinstance(best, Mapping):
        best_box = normalize_box(best["bbox"])
        for item in records:
            if normalize_box(item["bbox"]) == best_box:
                metrics["best_score"] = item.get("score")
                break
    return metrics


def _load_metadata(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        payload = payload.get("targets")
    if not isinstance(payload, list):
        raise ValueError("Target metadata must be a list or contain `targets`")
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.config.resolve() != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical config required: {CANONICAL_CONFIG}")
    contract_payload = json.loads(args.input_contract.read_text(encoding="utf-8"))
    if not isinstance(contract_payload, Mapping):
        raise ValueError("Detector input contract must be an object")
    contract = validate_fresh_contract_payload(contract_payload)
    accepted = _load_boxes(args.accepted_barlines)
    current = _load_boxes(args.final_barlines)
    targets = _resolve_targets(
        accepted_boxes=accepted,
        current_boxes=current,
        metadata=_load_metadata(args.target_metadata),
        accepted_iou=args.accepted_iou,
    )
    if not targets:
        raise ValueError("No focused missing targets")
    scored = _load_scored(args.cnn_scored)
    cnn_accepted = _load_boxes(args.cnn_accepted)
    output_rows = []
    details = []
    for target in targets:
        reference = normalize_box(target["accepted_bbox"])
        target_root = args.output_root / target["id"]
        trace = build_target_trace(
            Namespace(
                input_contract=args.input_contract,
                config=args.config,
                image=args.image,
                probe_image=args.probe_image,
                input_image_scale=args.input_image_scale,
                expected_image_sha256=args.expected_image_sha256,
                fresh_baseline=args.fresh_baseline,
                current_sr=args.current_sr,
                current_omr=args.current_omr,
                hybrid=args.hybrid,
                staff_mask=args.staff_mask,
                clef_mask=args.clef_mask,
                allow_zero_staff_mask=args.allow_zero_staff_mask,
                allow_zero_clef_mask=args.allow_zero_clef_mask,
                score=args.score,
                page=args.page,
                missing_reference=reference,
                nearby_reference=_nearest(reference, current),
                accepted_iou=args.accepted_iou,
                experimental_paper_side_context_width_ratio=0.0,
                consensus_iou=args.consensus_iou,
                vertical_iou_sweep=(0.0,),
                output_root=target_root,
            )
        )
        source = trace["source_trace"]["missing"]
        probe = trace["variants"]["suppression_default"]["targets"]["missing"]
        cnn_scored = _scored_metrics(reference, scored, args.accepted_iou)
        cnn_kept = target_metrics(
            reference, cnn_accepted, accepted_iou=args.accepted_iou
        )
        final = target_metrics(reference, current, accepted_iou=args.accepted_iou)
        boundary = _first_loss_boundary(
            source_trace=source,
            probe_trace=probe,
            cnn_scored=cnn_scored,
            cnn_accepted=cnn_kept,
            accepted_final=bool(final["accepted"]),
        )
        detail = {
            **target,
            "first_loss_boundary": boundary,
            "source_trace": source,
            "probe_trace": probe,
            "cnn_scored": cnn_scored,
            "cnn_accepted": cnn_kept,
            "current_final": final,
            "trace_report": str(target_root / "probe_boundary_report.json"),
        }
        details.append(detail)
        output_rows.append(
            {
                "score": args.score,
                "page": args.page,
                "system": target.get("system"),
                "target_id": target["id"],
                "accepted_bbox": json.dumps(list(reference)),
                "baseline_homr": source["fresh_baseline"]["accepted"],
                "sr_homr": source["current_sr"]["accepted"],
                "omr_dln": source["current_omr"]["accepted"],
                "hybrid": source["hybrid"]["accepted"],
                "raw_probe": probe["raw"]["accepted"],
                "filtered_candidate": probe["heuristic_filtered"]["accepted"],
                "cnn_score": cnn_scored.get("best_score"),
                "accepted_final": final["accepted"],
                "first_loss_boundary": boundary,
                "focused_fp_delta": target.get("focused_fp_delta"),
                "downstream_effect": target.get("downstream_effect"),
            }
        )
    report = {
        "schema_version": "issue255.focused_detector_inventory.v1",
        "status": "completed",
        "score": args.score,
        "page": args.page,
        "detector_input_contract": contract,
        "canonical_config": artifact_record(args.config),
        "effective_overrides": {},
        "accepted_reference_runtime_input": False,
        "inventory": details,
    }
    write_json(args.output_root / "focused_detector_inventory.json", report)
    csv_path = args.output_root / "focused_detector_inventory.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "input-contract",
        "image",
        "expected-image-sha256",
        "fresh-baseline",
        "current-sr",
        "current-omr",
        "hybrid",
        "cnn-scored",
        "cnn-accepted",
        "final-barlines",
        "accepted-barlines",
        "score",
        "page",
        "output-root",
    ):
        parser.add_argument(
            f"--{name}",
            type=None if name in {"expected-image-sha256", "score", "page"} else Path,
            required=True,
        )
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument("--probe-image", type=Path)
    parser.add_argument("--input-image-scale", type=float, default=2.0)
    parser.add_argument("--staff-mask", type=Path)
    parser.add_argument("--clef-mask", type=Path)
    parser.add_argument("--allow-zero-staff-mask", action="store_true")
    parser.add_argument("--allow-zero-clef-mask", action="store_true")
    parser.add_argument("--target-metadata", type=Path)
    parser.add_argument("--accepted-iou", type=float, default=0.5)
    parser.add_argument("--consensus-iou", type=float, default=0.5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        failure = {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
        write_json(args.output_root / "focused_detector_inventory.json", failure)
        print(json.dumps(failure))
        return 1
    print(json.dumps({"status": report["status"], "targets": len(report["inventory"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
