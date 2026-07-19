"""Pure helpers for the Issue #252 focused probe-boundary trace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from src.common import barline_iou
from src.pipeline.steps.candidate_filters import split_box_vertically
from src.pipeline.steps.probe_scan import _estimate_unit_size_from_existing_boxes

Box = tuple[int, int, int, int]


def normalize_box(value: Sequence[Any]) -> Box:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def validate_fresh_contract_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    nested = payload.get("detector_input_contract")
    contract = dict(nested if isinstance(nested, Mapping) else payload)
    errors = []
    if contract.get("mode") != "fresh_upstream":
        errors.append(f"mode={contract.get('mode')!r}")
    if contract.get("fresh_upstream_authoritative") is not True:
        errors.append(
            f"fresh_upstream_authoritative={contract.get('fresh_upstream_authoritative')!r}"
        )
    if contract.get("override_keys") != []:
        errors.append(f"override_keys={contract.get('override_keys')!r}")
    if errors:
        raise ValueError("Input contract is not authoritative fresh upstream: " + ", ".join(errors))
    return contract


def target_metrics(reference: Box, boxes: Iterable[Box], *, accepted_iou: float) -> dict[str, Any]:
    ref_cx = (reference[0] + reference[2]) / 2.0
    ref_cy = (reference[1] + reference[3]) / 2.0
    records = []
    for box in boxes:
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        records.append(
            {
                "bbox": list(box),
                "iou": float(barline_iou(reference, box)),
                "x_center_distance": abs(ref_cx - cx),
                "y_center_distance": abs(ref_cy - cy),
                "vertical_overlap_px": max(
                    0,
                    min(reference[3], box[3]) - max(reference[1], box[1]),
                ),
            }
        )
    records.sort(
        key=lambda item: (
            -item["iou"],
            item["x_center_distance"],
            item["y_center_distance"],
            item["bbox"],
        )
    )
    best = records[0] if records else None
    return {
        "count": len(records),
        "accepted": bool(best and best["iou"] > accepted_iou),
        "best": best,
        "x_aligned": [item for item in records if item["x_center_distance"] <= 12.0][:10],
    }


def _relevant_bands(row_stats: Sequence[Mapping[str, float]], reference: Box) -> list[list[int]]:
    center = (reference[1] + reference[3]) / 2.0
    result = []
    for stat in row_stats:
        top = int(round(float(stat["top"])))
        bottom = int(round(float(stat["bottom"])))
        if top <= center <= bottom or max(top, reference[1]) < min(bottom, reference[3]):
            result.append([top, bottom])
    return result


def _debug_records(debug_json: Path, reference: Box) -> list[dict[str, Any]]:
    if not debug_json.is_file():
        return []
    payload = load_json(debug_json)
    records = payload.get("records", []) if isinstance(payload, Mapping) else []
    target_x = (reference[0] + reference[2]) / 2.0
    target_y = (reference[1] + reference[3]) / 2.0
    result = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        col = record.get("col", record.get("seed_col"))
        if col is None or abs(float(col) - target_x) > 12.0:
            continue
        band = record.get("band") or record.get("staff_band")
        if isinstance(band, Sequence) and len(band) >= 2:
            if not float(band[0]) <= target_y <= float(band[1]):
                continue
        result.append(dict(record))
    return result[:20]


def stage_summary(
    *,
    reference: Box,
    stages: Mapping[str, Sequence[Box]],
    dropped: Sequence[Mapping[str, Any]],
    debug_json: Path,
    row_stats: Sequence[Mapping[str, float]],
    accepted_iou: float,
) -> dict[str, Any]:
    drop_matches = []
    for item in dropped:
        bbox = item.get("bbox")
        if not isinstance(bbox, Sequence):
            continue
        box = normalize_box(bbox)
        iou = float(barline_iou(reference, box))
        x_distance = abs(((reference[0] + reference[2]) - (box[0] + box[2])) / 2.0)
        if iou > 0 or x_distance <= 12.0:
            drop_matches.append(
                {
                    "bbox": list(box),
                    "iou": iou,
                    "x_center_distance": x_distance,
                    "reasons": list(item.get("reasons", [])),
                }
            )
    drop_matches.sort(key=lambda item: (-item["iou"], item["x_center_distance"]))
    return {
        "row_bands": _relevant_bands(row_stats, reference),
        **{
            name: target_metrics(reference, boxes, accepted_iou=accepted_iou)
            for name, boxes in stages.items()
        },
        "filter_drop_matches": drop_matches[:20],
        "debug_records": _debug_records(debug_json, reference),
    }


def classify_first_loss(
    *,
    source_trace: Mapping[str, Any],
    variants: Mapping[str, Mapping[str, Any]],
    target_name: str = "missing",
) -> dict[str, Any]:
    sources = source_trace[target_name]
    if not sources["fresh_baseline"]["accepted"]:
        return {"boundary": "baseline_homr", "recommended_variant": None}
    primary = (
        "after_hybrid_consensus"
        if sources["hybrid"]["accepted"]
        else "hybrid_consensus_support_loss"
    )
    base = variants["suppression_default"]["targets"][target_name]
    if base["final"]["accepted"]:
        return {
            "boundary": "already_recovered",
            "primary_loss": primary,
            "recommended_variant": None,
        }

    recovered = []
    for name, variant in variants.items():
        if name == "suppression_default":
            continue
        target = variant["targets"][target_name]
        if target["raw"]["accepted"] or target["final"]["accepted"]:
            recovered.append((name, variant, target))
    if not base["raw"]["accepted"] and recovered:
        recovered.sort(
            key=lambda item: (
                0 if item[2]["final"]["accepted"] else 1,
                float(item[1].get("vertical_iou", 1.0)),
                item[0],
            )
        )
        name, _, target = recovered[0]
        return {
            "boundary": "existing_box_suppression",
            "primary_loss": primary,
            "recommended_variant": name,
            "candidate_reaches_final": target["final"]["accepted"],
        }

    if not base["row_bands"]:
        boundary = "row_band_construction"
    elif not base["raw"]["accepted"]:
        boundary = "raw_probe_generation"
    elif not base["size_filtered"]["accepted"]:
        boundary = "size_filter"
    elif not base["heuristic_filtered"]["accepted"]:
        boundary = "candidate_filter"
    elif not base["trimmed"]["accepted"]:
        boundary = "trim"
    else:
        boundary = "final_set_or_dedup"
    return {
        "boundary": boundary,
        "primary_loss": primary,
        "recommended_variant": None,
    }


def split_tall_existing_boxes(
    image: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    ink_threshold: int,
) -> list[Box]:
    unit_size = _estimate_unit_size_from_existing_boxes(existing_boxes) or 40.0
    split_threshold = 12.0 * unit_size
    output = []
    for box in existing_boxes:
        if abs(box[3] - box[1]) <= split_threshold:
            output.append(box)
        else:
            output.extend(
                normalize_box(item)
                for item in split_box_vertically(
                    image,
                    box,
                    ink_threshold=ink_threshold,
                    min_gap=int(1.25 * unit_size),
                    min_segment_h=int(0.75 * unit_size),
                )
            )
    return output
